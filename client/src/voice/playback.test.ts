import { beforeEach, describe, expect, it, vi } from "vitest";
import type { VoiceAudioMetadata } from "../types";
import { VoicePlaybackQueue } from "./playback";

class FakeAudio {
  static instances: FakeAudio[] = [];
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  pause = vi.fn();
  play = vi.fn(async () => undefined);

  constructor(public readonly src: string) {
    FakeAudio.instances.push(this);
  }
}

function metadata(index: number, kind: "status" | "response" = "response"): VoiceAudioMetadata {
  return {
    requestId: "req",
    groupId: `req-${kind}`,
    audioId: `${kind}-${index}`,
    mimeType: "audio/mpeg",
    index,
    total: 2,
    kind
  };
}

describe("VoicePlaybackQueue", () => {
  const createUrl = vi.fn((blob: Blob) => `blob:${blob.size}:${createUrl.mock.calls.length}`);
  const revokeUrl = vi.fn();

  beforeEach(() => {
    FakeAudio.instances = [];
    createUrl.mockClear();
    revokeUrl.mockClear();
    vi.stubGlobal("Audio", FakeAudio);
    vi.stubGlobal("URL", { createObjectURL: createUrl, revokeObjectURL: revokeUrl });
  });

  it("plays progressively arriving response segments in order", async () => {
    const playing: boolean[] = [];
    const queue = new VoicePlaybackQueue((value) => playing.push(value), vi.fn());
    queue.enqueue(metadata(0), new ArrayBuffer(2));
    queue.enqueue(metadata(1), new ArrayBuffer(2));
    await Promise.resolve();
    expect(FakeAudio.instances).toHaveLength(1);
    FakeAudio.instances[0].onended?.();
    await Promise.resolve();
    expect(FakeAudio.instances).toHaveLength(2);
    expect(playing).toContain(true);
  });

  it("stops and revokes current plus queued audio", async () => {
    const queue = new VoicePlaybackQueue(vi.fn(), vi.fn());
    queue.enqueue(metadata(0), new ArrayBuffer(2));
    queue.enqueue(metadata(1), new ArrayBuffer(2));
    await Promise.resolve();
    queue.stop();
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledOnce();
    expect(revokeUrl).toHaveBeenCalledTimes(2);
    expect(queue.isPlaying).toBe(false);
  });

  it("drops stale status playback when a final response arrives", async () => {
    const queue = new VoicePlaybackQueue(vi.fn(), vi.fn());
    queue.enqueue(metadata(0, "status"), new ArrayBuffer(2));
    await Promise.resolve();
    queue.enqueue(metadata(0, "response"), new ArrayBuffer(2));
    await Promise.resolve();
    expect(FakeAudio.instances[0].pause).toHaveBeenCalledOnce();
    expect(FakeAudio.instances).toHaveLength(2);
  });
});
