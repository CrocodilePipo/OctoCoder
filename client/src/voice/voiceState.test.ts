import { describe, expect, it } from "vitest";
import { isNoSpeechVoiceError, PCMActivityMeter, VoiceSessionState } from "./voiceState";

describe("VoiceSessionState", () => {
  it("sends finish and accepts the final transcript exactly once", () => {
    const state = new VoiceSessionState();
    state.begin("req-1", "hold");
    expect(state.ready()).toBe(true);
    expect(state.finish()).toBe(true);
    expect(state.finish()).toBe(false);
    expect(state.transcript("req-1", "first")).toBe(true);
    expect(state.transcript("req-1", "duplicate")).toBe(false);
    expect(state.caption).toBe("first");
  });

  it("rejects stale request IDs and transcript revisions", () => {
    const state = new VoiceSessionState();
    state.begin("current", "continuous");
    state.ready();
    expect(state.partial("stale", "wrong", 1)).toBe(false);
    expect(state.partial("current", "hello", 2)).toBe(true);
    expect(state.partial("current", "older", 1)).toBe(false);
    expect(state.caption).toBe("hello");
  });

  it("assigns strictly increasing frame sequence numbers", () => {
    const state = new VoiceSessionState();
    state.begin("req", "hold");
    state.ready();
    expect([state.nextFrameSequence(), state.nextFrameSequence()]).toEqual([0, 1]);
  });
});

describe("PCMActivityMeter", () => {
  function frame(value: number, samples = 320): ArrayBuffer {
    return new Int16Array(samples).fill(value).buffer;
  }

  it("rejects empty, short, and silent captures", () => {
    const meter = new PCMActivityMeter();
    expect(meter.canSubmit()).toBe(false);
    for (let index = 0; index < 10; index += 1) meter.addFrame(frame(0));
    expect(meter.canSubmit()).toBe(false);
    meter.reset();
    meter.addFrame(frame(1200));
    meter.addFrame(frame(1200));
    expect(meter.canSubmit()).toBe(false);
  });

  it("accepts a capture with enough duration and voiced frames", () => {
    const meter = new PCMActivityMeter();
    for (let index = 0; index < 8; index += 1) meter.addFrame(frame(0));
    meter.addFrame(frame(1200));
    meter.addFrame(frame(1200));
    expect(meter.canSubmit()).toBe(true);
  });
});

describe("isNoSpeechVoiceError", () => {
  it("normalizes empty recording and empty ASR results", () => {
    expect(isNoSpeechVoiceError("Recording is empty")).toBe(true);
    expect(isNoSpeechVoiceError("Aliyun realtime ASR returned no text")).toBe(true);
    expect(isNoSpeechVoiceError("HTTP 401")).toBe(false);
  });
});
