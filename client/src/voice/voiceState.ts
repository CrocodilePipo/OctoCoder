import type { VoicePhase } from "../types";

export type VoiceInputMode = "hold" | "continuous";

const MIN_CAPTURE_SAMPLES = 3200;
const MIN_VOICED_FRAMES = 2;
const MIN_VOICED_RMS = 180;

export class PCMActivityMeter {
  totalSamples = 0;
  voicedFrames = 0;

  addFrame(frame: ArrayBuffer): void {
    const samples = new Int16Array(frame, 0, Math.floor(frame.byteLength / 2));
    if (!samples.length) return;
    let squareSum = 0;
    for (const sample of samples) squareSum += sample * sample;
    this.totalSamples += samples.length;
    if (Math.sqrt(squareSum / samples.length) >= MIN_VOICED_RMS) this.voicedFrames += 1;
  }

  canSubmit(): boolean {
    return this.totalSamples >= MIN_CAPTURE_SAMPLES && this.voicedFrames >= MIN_VOICED_FRAMES;
  }

  reset(): void {
    this.totalSamples = 0;
    this.voicedFrames = 0;
  }
}

export function isNoSpeechVoiceError(message: string): boolean {
  const normalized = message.toLowerCase();
  return normalized.includes("recording is empty") ||
    normalized.includes("returned no text") ||
    normalized.includes("no speech") ||
    normalized.includes("未识别到语音");
}

export class VoiceSessionState {
  requestId = "";
  mode: VoiceInputMode = "hold";
  phase: VoicePhase = "idle";
  caption = "";
  sequence = 0;
  private finishSent = false;
  private transcriptReceived = false;
  private revision = 0;

  begin(requestId: string, mode: VoiceInputMode): void {
    if (this.requestId) throw new Error("A voice stream is already active.");
    this.requestId = requestId;
    this.mode = mode;
    this.phase = "connecting";
    this.caption = "";
    this.sequence = 0;
    this.finishSent = false;
    this.transcriptReceived = false;
    this.revision = 0;
  }

  ready(): boolean {
    if (!this.requestId || this.finishSent) return false;
    this.phase = "recording";
    return true;
  }

  nextFrameSequence(): number {
    const current = this.sequence;
    this.sequence += 1;
    return current;
  }

  finish(): boolean {
    if (!this.requestId || this.finishSent) return false;
    this.finishSent = true;
    this.phase = "transcribing";
    return true;
  }

  partial(requestId: string, text: string, revision: number): boolean {
    if (requestId !== this.requestId || revision <= this.revision || this.transcriptReceived) return false;
    this.revision = revision;
    this.caption = text;
    return true;
  }

  transcript(requestId: string, text: string): boolean {
    if (requestId !== this.requestId || this.transcriptReceived) return false;
    this.transcriptReceived = true;
    this.caption = text;
    return true;
  }

  reset(phase: VoicePhase = "idle"): void {
    this.requestId = "";
    this.phase = phase;
    this.caption = "";
    this.sequence = 0;
    this.finishSent = false;
    this.transcriptReceived = false;
    this.revision = 0;
  }
}
