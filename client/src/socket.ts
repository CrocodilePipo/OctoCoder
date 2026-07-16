import type { ClientMessage, ServerMessage } from "./types";

export type SocketCallbacks = {
  onOpen: () => void;
  onClose: () => void;
  onMessage: (message: ServerMessage) => void;
};

export class OctoCoderSocket {
  private socket: WebSocket | null = null;
  private pingTimer = 0;
  private reconnectTimer = 0;
  private closedByUser = false;

  constructor(private readonly callbacks: SocketCallbacks) {}

  connect(): void {
    this.closedByUser = false;
    this.clearTimers();
    this.socket?.close();

    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get("ws") || "";
    const explicit = fromQuery || (import.meta.env.VITE_OCTOCODER_WS_URL as string | undefined);
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = explicit || `${protocol}//${window.location.host}/ws`;
    this.socket = new WebSocket(url);

    this.socket.onopen = () => {
      this.callbacks.onOpen();
      this.pingTimer = window.setInterval(() => this.send({ type: "ping", data: {} }), 10_000);
    };

    this.socket.onmessage = (event) => {
      try {
        this.callbacks.onMessage(JSON.parse(event.data) as ServerMessage);
      } catch {
        // Ignore malformed server messages; the backend logs its side.
      }
    };

    this.socket.onclose = () => {
      this.callbacks.onClose();
      this.clearTimers();
      if (!this.closedByUser) {
        this.reconnectTimer = window.setTimeout(() => this.connect(), 2_000);
      }
    };
  }

  disconnect(): void {
    this.closedByUser = true;
    this.clearTimers();
    this.socket?.close();
    this.socket = null;
  }

  send(message: ClientMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  private clearTimers(): void {
    if (this.pingTimer) window.clearInterval(this.pingTimer);
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.pingTimer = 0;
    this.reconnectTimer = 0;
  }
}
