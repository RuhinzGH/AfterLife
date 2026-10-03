import { Component } from "react";

// Without this, an uncaught render error ANYWHERE in the tree unmounts the
// entire app -- sidebar, nav, everything -- leaving a blank page with no way
// back except a hard reload. Wrapping the main content area means a bug in
// one tab shows a real error there while the rest of the app (nav, account
// button) stays usable, so you can at least navigate away from the broken view.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Render error caught by ErrorBoundary:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card pad-lg">
          <div className="badge bad">⚠ Something broke on this page</div>
          <p className="note" style={{ marginTop: "0.8rem" }}>
            {this.state.error.message || "An unexpected error occurred."}
          </p>
          <button className="ghost" style={{ marginTop: "0.9rem" }} onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
