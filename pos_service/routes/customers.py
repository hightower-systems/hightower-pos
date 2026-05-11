from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from pos_service.auth import get_current_user
from pos_service.clients.fabric import (
    FabricClient,
    FabricClientError,
    get_fabric_client,
)
from pos_service.models import POSUser

router = APIRouter(prefix="/api/customers", tags=["customers"])


class CustomerLookupResponse(BaseModel):
    customer_id: str | None
    display_name: str | None
    email: str | None
    phone: str | None
    registered: bool


class CreateCustomerRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class CreateCustomerResponse(BaseModel):
    customer_id: str
    display_name: str | None
    email: str | None
    phone: str | None
    registered: bool


@router.get("/lookup", response_model=CustomerLookupResponse | None)
async def lookup_customer(
    name: str | None = Query(default=None, max_length=128),
    email: str | None = Query(default=None, max_length=128),
    phone: str | None = Query(default=None, max_length=64),
    fabric: FabricClient = Depends(get_fabric_client),
    user: POSUser = Depends(get_current_user),
) -> CustomerLookupResponse | None:
    if not (name or email or phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "at_least_one_query_param_required"},
        )
    try:
        match = await fabric.lookup_customer(name=name, email=email, phone=phone)
    except FabricClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "fabric_unavailable", "message": str(exc)},
        ) from exc
    if match is None:
        return None
    return CustomerLookupResponse(
        customer_id=match.get("customer_id"),
        display_name=match.get("display_name") or match.get("name"),
        email=match.get("email"),
        phone=match.get("phone"),
        registered=bool(match.get("registered", False)),
    )


@router.post("", response_model=CreateCustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(
    body: CreateCustomerRequest,
    fabric: FabricClient = Depends(get_fabric_client),
    user: POSUser = Depends(get_current_user),
) -> CreateCustomerResponse:
    """Create a customer in Fabric and hand back the new id + display
    fields. Used by the cashier UI when a lookup returns no match and
    the cashier wants the customer registered (vs. just attaching as
    an unregistered ride-along on the sale)."""
    name = (body.name or "").strip() or None
    email = (body.email or "").strip() or None
    phone = (body.phone or "").strip() or None
    if not (name or email or phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "at_least_one_field_required"},
        )
    try:
        created = await fabric.create_customer(name=name, email=email, phone=phone)
    except FabricClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "fabric_unavailable", "message": str(exc)},
        ) from exc
    customer_id = created.get("customer_id")
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "fabric_returned_no_customer_id"},
        )
    return CreateCustomerResponse(
        customer_id=str(customer_id),
        display_name=created.get("display_name") or created.get("name") or name,
        email=created.get("email") or email,
        phone=created.get("phone") or phone,
        registered=bool(created.get("registered", True)),
    )
