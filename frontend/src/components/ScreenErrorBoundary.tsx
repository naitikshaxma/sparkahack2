import { Component, ReactNode } from "react";

type Props = {
  children: ReactNode;
  onRecover: () => void;
};

type State = {
  hasError: boolean;
};

class ScreenErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown): void {
    console.error("voice_screen_runtime_error", error);
  }

  handleRecover = (): void => {
    this.setState({ hasError: false });
    this.props.onRecover();
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center px-4">
        <div className="w-full max-w-xl rounded-2xl border border-white/15 bg-white/5 p-6 text-center space-y-4">
          <h2 className="text-2xl font-semibold">Something went wrong</h2>
          <p className="text-sm text-gray-300">The voice screen crashed unexpectedly. Please return and select a language again.</p>
          <button
            type="button"
            onClick={this.handleRecover}
            className="h-11 rounded-xl px-5 border border-amber-300/50 text-amber-200 hover:bg-amber-300/10"
          >
            Back to language selection
          </button>
        </div>
      </div>
    );
  }
}

export default ScreenErrorBoundary;