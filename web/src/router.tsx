import { createBrowserRouter } from "react-router";

import { RouteError } from "./pages/RouteError";

export const router = createBrowserRouter([
  {
    path: "/pay/:invoiceId",
    ErrorBoundary: RouteError,
    lazy: async () => ({ Component: (await import("./pages/PayPage")).PayPage }),
  },
  {
    path: "/",
    ErrorBoundary: RouteError,
    lazy: async () => ({ Component: (await import("./pages/Landing")).Landing }),
  },
  {
    path: "/shop",
    ErrorBoundary: RouteError,
    lazy: async () => ({ Component: (await import("./features/shop/ShopLayout")).ShopLayout }),
    children: [
      {
        index: true,
        lazy: async () => ({ Component: (await import("./features/shop/Catalog")).Catalog }),
      },
      {
        path: "orders/:orderId",
        lazy: async () => ({ Component: (await import("./features/shop/OrderPage")).OrderPage }),
      },
    ],
  },
  {
    path: "/login",
    lazy: async () => ({ Component: (await import("./features/dashboard/Login")).Login }),
  },
  {
    path: "/dashboard",
    ErrorBoundary: RouteError,
    lazy: async () => ({
      Component: (await import("./features/dashboard/DashboardLayout")).DashboardLayout,
    }),
    children: [
      {
        index: true,
        lazy: async () => ({ Component: (await import("./features/dashboard/Overview")).Overview }),
      },
      {
        path: "invoices",
        lazy: async () => ({ Component: (await import("./features/dashboard/Invoices")).Invoices }),
      },
      {
        path: "invoices/:invoiceId",
        lazy: async () => ({
          Component: (await import("./features/dashboard/InvoiceDetail")).InvoiceDetailPage,
        }),
      },
      {
        path: "review",
        lazy: async () => ({ Component: (await import("./features/dashboard/Review")).Review }),
      },
      {
        path: "webhooks",
        lazy: async () => ({ Component: (await import("./features/dashboard/Webhooks")).Webhooks }),
      },
      {
        path: "developers",
        lazy: async () => ({
          Component: (await import("./features/dashboard/Developers")).Developers,
        }),
      },
      {
        path: "settings",
        lazy: async () => ({ Component: (await import("./features/dashboard/Settings")).Settings }),
      },
    ],
  },
  {
    path: "*",
    lazy: async () => ({ Component: (await import("./pages/NotFound")).NotFound }),
  },
]);
