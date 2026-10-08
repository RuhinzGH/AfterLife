import React from "react";
import ReactDOM from "react-dom/client";
// The redesigned site. The original shell (App.jsx) is kept, unused, so the
// change is easy to undo: swap this import back.
import App from "./v2/AppV2.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
