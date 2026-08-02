import type { ClientMessage, ServerMessage, VoiceAudioMetadata } from "./types";

export type SocketCallbacks = {
  onOpen: () => void;
  onClose: () => void;
  onMessage: (message: ServerMessage) => void;
  onVoiceAudio: (metadata: VoiceAudioMetadata, data: ArrayBuffer) => void;
};

export class OctoCoderSocket {
  private socket: WebSocket | null = null;
  private pingTimer = 0;
  private reconnectTimer = 0;
  private closedByUser = false;
  private pendingVoiceAudio: VoiceAudioMetadata | null = null;

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
    this.socket.binaryType = "arraybuffer";

    this.socket.onopen = () => {
      this.callbacks.onOpen();
      this.pingTimer = window.setInterval(() => this.send({ type: "ping", data: {} }), 10_000);
    };

    this.socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        try {
          const message = JSON.parse(event.data) as ServerMessage;
          if (message.type === "voice_audio_start") {
            this.pendingVoiceAudio = message.data;
          }
          this.callbacks.onMessage(message);
        } catch {
          // Ignore malformed server messages; the backend logs its side.
        }
        return;
      }
      void this.receiveBinary(event.data);
    };

    this.socket.onclose = () => {
      this.callbacks.onClose();
      this.pendingVoiceAudio = null;
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

  send(message: ClientMessage): boolean {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
      return true;
    }
    return false;
  }

  sendBinary(data: ArrayBuffer | Blob): boolean {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(data);
      return true;
    }
    return false;
  }

  sendVoiceFrame(requestId: string, sequence: number, data: ArrayBuffer): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({
      type: "voice_stream_chunk",
      data: { requestId, sequence, byteLength: data.byteLength }
    } satisfies ClientMessage));
    this.socket.send(data);
    return true;
  }

  private async receiveBinary(data: unknown): Promise<void> {
    const metadata = this.pendingVoiceAudio;
    this.pendingVoiceAudio = null;
    if (!metadata) return;
    if (data instanceof ArrayBuffer) {
      this.callbacks.onVoiceAudio(metadata, data);
      return;
    }
    if (data instanceof Blob) {
      this.callbacks.onVoiceAudio(metadata, await data.arrayBuffer());
    }
  }

  private clearTimers(): void {
    if (this.pingTimer) window.clearInterval(this.pingTimer);
    if (this.reconnectTimer) window.clearTimeout(this.reconnectTimer);
    this.pingTimer = 0;
    this.reconnectTimer = 0;
  }
}
