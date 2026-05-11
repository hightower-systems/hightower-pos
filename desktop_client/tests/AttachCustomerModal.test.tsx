import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";

import { AttachCustomerModal } from "../src/components/AttachCustomerModal";
import { useCustomer } from "../src/store/customer";
import { server } from "./msw/server";
import { renderWithQuery } from "./utils";

const API = "http://localhost";

beforeEach(() => useCustomer.getState().reset());
afterEach(() => useCustomer.getState().reset());

describe("<AttachCustomerModal>", () => {
  it("returns null when phase is idle", () => {
    const { container } = renderWithQuery(<AttachCustomerModal />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the lookup form when phase is lookup", () => {
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);
    expect(screen.getByLabelText(/customer name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/customer email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/customer phone/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /look up/i })).toBeDisabled();
  });

  it("look-up button enables when any field has content", async () => {
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);
    await userEvent.type(screen.getByLabelText(/customer email/i), "p@x.com");
    expect(screen.getByRole("button", { name: /look up/i })).toBeEnabled();
  });

  it("renders the registered match panel and 'Attach Existing Customer' button on a hit", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json({
          customer_id: "cust-1",
          display_name: "Pat Smith",
          email: "pat@example.com",
          phone: "+13035551234",
          registered: true,
        }),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer email/i), "pat@x.com");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));

    expect(await screen.findByTestId("customer-match")).toHaveTextContent(
      /registered customer/i,
    );
    expect(
      screen.getByRole("button", { name: /attach existing customer/i }),
    ).toBeEnabled();
  });

  it("attaches the matched customer and closes the modal on Attach Existing", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json({
          customer_id: "cust-1",
          display_name: "Pat Smith",
          email: "pat@example.com",
          phone: null,
          registered: true,
        }),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer email/i), "pat@x.com");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));
    await screen.findByTestId("customer-match");
    await userEvent.click(
      screen.getByRole("button", { name: /attach existing customer/i }),
    );

    await waitFor(() => {
      expect(useCustomer.getState().attached).not.toBeNull();
    });
    expect(useCustomer.getState().attached?.customer_id).toBe("cust-1");
    expect(useCustomer.getState().attached?.registered).toBe(true);
    expect(useCustomer.getState().phase).toBe("idle");
  });

  it("shows the no-match panel with 'Create Customer' + 'Attach As Typed' buttons", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json(null),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer name/i), "Brand New");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));

    expect(await screen.findByTestId("customer-no-match")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /create customer/i }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: /attach as typed/i }),
    ).toBeEnabled();
  });

  it("'Attach As Typed' attaches the typed values as unregistered (no Fabric create)", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json(null),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer name/i), "Brand New");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));
    await screen.findByTestId("customer-no-match");
    await userEvent.click(
      screen.getByRole("button", { name: /attach as typed/i }),
    );

    await waitFor(() => {
      expect(useCustomer.getState().attached).not.toBeNull();
    });
    expect(useCustomer.getState().attached?.customer_id).toBeNull();
    expect(useCustomer.getState().attached?.name).toBe("Brand New");
    expect(useCustomer.getState().attached?.registered).toBe(false);
  });

  it("'Create Customer' POSTs to /api/customers, attaches the new customer_id, closes the modal", async () => {
    let createBody: unknown = null;
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json(null),
      ),
      http.post(`${API}/api/customers`, async ({ request }) => {
        createBody = await request.json();
        return HttpResponse.json(
          {
            customer_id: "cust-new-42",
            display_name: "Brand New",
            email: "bn@example.com",
            phone: "5551111",
            registered: true,
          },
          { status: 201 },
        );
      }),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    const u = userEvent.setup();
    await u.type(screen.getByLabelText(/customer name/i), "Brand New");
    await u.type(screen.getByLabelText(/customer email/i), "bn@example.com");
    await u.type(screen.getByLabelText(/customer phone/i), "5551111");
    await u.click(screen.getByRole("button", { name: /look up/i }));
    await screen.findByTestId("customer-no-match");
    await u.click(screen.getByTestId("customer-create-button"));

    await waitFor(() => {
      expect(useCustomer.getState().attached).not.toBeNull();
    });
    expect(useCustomer.getState().attached?.customer_id).toBe("cust-new-42");
    expect(useCustomer.getState().attached?.registered).toBe(true);
    expect(useCustomer.getState().phase).toBe("idle");
    expect(createBody).toEqual({
      name: "Brand New",
      email: "bn@example.com",
      phone: "5551111",
    });
  });

  it("'Create Customer' surfaces an error and does NOT attach on 503", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json(null),
      ),
      http.post(`${API}/api/customers`, () =>
        HttpResponse.json(
          { detail: { error: "fabric_unavailable" } },
          { status: 503 },
        ),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer name/i), "Brand New");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));
    await screen.findByTestId("customer-no-match");
    await userEvent.click(screen.getByTestId("customer-create-button"));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(useCustomer.getState().attached).toBeNull();
  });

  it("Cancel closes without attaching", async () => {
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer name/i), "Pat");
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));

    expect(useCustomer.getState().phase).toBe("idle");
    expect(useCustomer.getState().attached).toBeNull();
  });

  it("renders an alert on a 503 lookup failure", async () => {
    server.use(
      http.get(`${API}/api/customers/lookup`, () =>
        HttpResponse.json(
          { detail: { error: "fabric_unavailable" } },
          { status: 503 },
        ),
      ),
    );
    useCustomer.getState().openLookup();
    renderWithQuery(<AttachCustomerModal />);

    await userEvent.type(screen.getByLabelText(/customer email/i), "x@y.com");
    await userEvent.click(screen.getByRole("button", { name: /look up/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
