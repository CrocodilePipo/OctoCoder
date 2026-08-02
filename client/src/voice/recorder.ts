export const MAX_RECORDING_SECONDS = 120;

export type PCMFrameHandler = (frame: ArrayBuffer) => void;

function voiceAsset(name: string): string {
  return new URL(`./voice/${name}`, window.location.href).href;
}

export class PCMStreamRecorder {
  private stream: MediaStream | null = null;
  private context: AudioContext | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private processor: AudioWorkletNode | null = null;
  private mute: GainNode | null = null;
  private limitTimer = 0;

  static isSupported(): boolean {
    return Boolean(
      "mediaDevices" in navigator &&
      window.AudioContext &&
      "audioWorklet" in AudioContext.prototype
    );
  }

  async start(onFrame: PCMFrameHandler, onTimeLimit: () => void): Promise<void> {
    if (!PCMStreamRecorder.isSupported()) {
      throw new Error("This device does not support realtime microphone capture.");
    }
    if (this.stream) throw new Error("A recording is already active.");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      },
      video: false
    });
    try {
      const context = new AudioContext({ latencyHint: "interactive" });
      await context.audioWorklet.addModule(voiceAsset("octocoder-pcm-worklet.js"));
      const source = context.createMediaStreamSource(stream);
      const processor = new AudioWorkletNode(context, "octocoder-pcm-processor", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        outputChannelCount: [1]
      });
      const mute = context.createGain();
      mute.gain.value = 0;
      processor.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (event.data instanceof ArrayBuffer && event.data.byteLength) onFrame(event.data);
      };
      source.connect(processor);
      processor.connect(mute);
      mute.connect(context.destination);
      this.stream = stream;
      this.context = context;
      this.source = source;
      this.processor = processor;
      this.mute = mute;
      this.limitTimer = window.setTimeout(onTimeLimit, MAX_RECORDING_SECONDS * 1000);
      if (context.state === "suspended") await context.resume();
    } catch (error) {
      stream.getTracks().forEach((track) => track.stop());
      await this.cleanup();
      throw error;
    }
  }

  async stop(): Promise<void> {
    if (!this.stream) throw new Error("No recording is active.");
    await this.cleanup();
  }

  cancel(): void {
    void this.cleanup();
  }

  dispose(): void {
    this.cancel();
  }

  private async cleanup(): Promise<void> {
    if (this.limitTimer) window.clearTimeout(this.limitTimer);
    this.limitTimer = 0;
    if (this.processor) this.processor.port.onmessage = null;
    this.processor?.disconnect();
    this.source?.disconnect();
    this.mute?.disconnect();
    this.stream?.getTracks().forEach((track) => track.stop());
    const context = this.context;
    this.stream = null;
    this.context = null;
    this.source = null;
    this.processor = null;
    this.mute = null;
    if (context && context.state !== "closed") await context.close();
  }
}

export function float32ToPCM16(samples: Float32Array): ArrayBuffer {
  const pcm = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    pcm[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
  }
  return pcm.buffer;
}

export function voiceAssetBase(): string {
  return voiceAsset("");
}
