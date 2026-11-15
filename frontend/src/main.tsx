import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { AppProvider } from "./lib/store";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProvider>
      <App />
    </AppProvider>
  </StrictMode>,
);

// Progressive Web App: cache the application shell so a previously loaded ASTRA opens without network.
// Health data is never cached by the service worker (see public/sw.js).
if ("serviceWorker" in navigator && window.isSecureContext && location.port !== "5173") {
  window.addEventListener("load", () => { navigator.serviceWorker.register("/sw.js").catch(() => { /* optional */ }); });
}
