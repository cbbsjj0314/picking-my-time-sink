import { createBrowserRouter, redirect } from "react-router-dom";

import { AppShell } from "./layout/AppShell";
import { GameDetailPage, gameDetailLoader } from "./pages/GameDetailPage";
import { OverviewPage, overviewLoader } from "./pages/OverviewPage";
import { RouteErrorPage } from "./pages/RouteErrorPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        index: true,
        loader: async () => redirect("/overview"),
      },
      {
        path: "overview",
        loader: overviewLoader,
        element: <OverviewPage />,
      },
      {
        path: "games/:canonical_game_id",
        loader: gameDetailLoader,
        element: <GameDetailPage />,
      },
    ],
  },
]);
