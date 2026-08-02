import type { VoiceAudioMetadata } from "../types";

type QueueItem = {
  metadata: VoiceAudioMetadata;
  url: string;
};

export class VoicePlaybackQueue {
  private queue: QueueItem[] = [];
  private current: QueueItem | null = null;
  private audio: HTMLAudioElement | null = null;

  constructor(
    private readonly onPlayingChange: (playing: boolean) => void,
    private readonly onError: (message: string) => void
  ) {}

  enqueue(metadata: VoiceAudioMetadata, data: ArrayBuffer): void {
    if (metadata.kind === "response" && (
      this.current?.metadata.kind === "status" ||
      this.queue.some((item) => item.metadata.kind === "status")
    )) {
      this.stop();
    }
    const url = URL.createObjectURL(new Blob([data], { type: metadata.mimeType || "audio/mpeg" }));
    this.queue.push({ metadata, url });
    this.queue.sort((left, right) => {
      if (left.metadata.groupId !== right.metadata.groupId) return 0;
      return left.metadata.index - right.metadata.index;
    });
    if (!this.audio) void this.playNext();
  }

  get isPlaying(): boolean {
    return Boolean(this.audio || this.queue.length);
  }

  stop(): void {
    if (this.audio) {
      this.audio.pause();
      this.audio.onended = null;
      this.audio.onerror = null;
      this.audio = null;
    }
    if (this.current) {
      URL.revokeObjectURL(this.current.url);
      this.current = null;
    }
    for (const item of this.queue) URL.revokeObjectURL(item.url);
    this.queue = [];
    this.onPlayingChange(false);
  }

  dispose(): void {
    this.stop();
  }

  private async playNext(): Promise<void> {
    const item = this.queue.shift();
    if (!item) {
      this.current = null;
      this.audio = null;
      this.onPlayingChange(false);
      return;
    }

    this.current = item;
    const audio = new Audio(item.url);
    this.audio = audio;
    this.onPlayingChange(true);
    audio.onended = () => this.finishCurrent();
    audio.onerror = () => {
      this.onError("Voice playback failed.");
      this.finishCurrent();
    };
    try {
      await audio.play();
    } catch (error) {
      this.onError(error instanceof Error ? error.message : "Voice playback was blocked.");
      this.finishCurrent();
    }
  }

  private finishCurrent(): void {
    if (this.current) URL.revokeObjectURL(this.current.url);
    this.current = null;
    this.audio = null;
    void this.playNext();
  }
}
