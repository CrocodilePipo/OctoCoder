import { MicVAD } from "@ricky0123/vad-web";
import { float32ToPCM16, voiceAssetBase } from "./recorder";

type ContinuousCallbacks = {
  onSpeechStart: (preSpeechFrames: ArrayBuffer[]) => void;
  onSpeechFrame: (frame: ArrayBuffer) => void;
  onSpeechEnd: () => void;
  onMisfire: () => void;
};

export class ContinuousVoiceDetector {
  private vad: MicVAD | null = null;
  private speaking = false;
  private ring: Float32Array[] = [];
  private callbacks: ContinuousCallbacks | null = null;

  get active(): boolean {
    return Boolean(this.vad?.listening);
  }

  async start(silenceMs: number, callbacks: ContinuousCallbacks): Promise<void> {
    this.callbacks = callbacks;
    if (!this.vad) {
      const assetBase = voiceAssetBase();
      this.vad = await MicVAD.new({
        model: "v5",
        startOnLoad: false,
        processorType: "AudioWorklet",
        baseAssetPath: assetBase,
        onnxWASMBasePath: assetBase,
        redemptionMs: silenceMs,
        preSpeechPadMs: 320,
        minSpeechMs: 280,
        submitUserSpeechOnPause: false,
        onSpeechStart: () => {
          this.speaking = true;
          const preSpeech = this.ring.map((frame) => float32ToPCM16(frame));
          this.callbacks?.onSpeechStart(preSpeech);
        },
        onSpeechRealStart: () => undefined,
        onFrameProcessed: (_probabilities, frame) => {
          if (this.speaking) {
            this.callbacks?.onSpeechFrame(float32ToPCM16(frame));
            return;
          }
          this.ring.push(new Float32Array(frame));
          while (this.ring.length > 10) this.ring.shift();
        },
        onSpeechEnd: () => {
          this.speaking = false;
          this.ring = [];
          this.callbacks?.onSpeechEnd();
        },
        onVADMisfire: () => {
          this.speaking = false;
          this.ring = [];
          this.callbacks?.onMisfire();
        }
      });
    } else {
      this.vad.setOptions({ redemptionMs: silenceMs });
    }
    await this.vad.start();
  }

  async pause(): Promise<void> {
    this.speaking = false;
    this.ring = [];
    if (this.vad?.listening) await this.vad.pause();
  }

  destroy(): void {
    this.speaking = false;
    this.ring = [];
    this.callbacks = null;
    this.vad?.destroy();
    this.vad = null;
  }
}
