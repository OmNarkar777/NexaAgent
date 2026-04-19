import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import CustomerChat   from "./pages/CustomerChat";
import AgentDashboard from "./pages/AgentDashboard";
import OpsDashboard   from "./pages/OpsDashboard";
import "./styles/index.css";
const qc = new QueryClient({ defaultOptions: { queries: { staleTime: 30000 } } });
ReactDOM.createRoot(document.getElementById("root")).render(
  <QueryClientProvider client={qc}>
    <BrowserRouter>
      <Routes>
        <Route path="/"      element={<CustomerChat />} />
        <Route path="/agent" element={<AgentDashboard />} />
        <Route path="/ops"   element={<OpsDashboard />} />
        <Route path="*"      element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  </QueryClientProvider>
);