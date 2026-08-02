class OctoCoderPCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.samples = [];
    this.position = 0;
    this.output = [];
    this.ratio = sampleRate / 16000;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel || channel.length === 0) return true;
    for (let index = 0; index < channel.length; index += 1) {
      this.samples.push(channel[index]);
    }
    while (this.position + 1 < this.samples.length) {
      const left = Math.floor(this.position);
      const fraction = this.position - left;
      const sample = this.samples[left] * (1 - fraction) + this.samples[left + 1] * fraction;
      this.output.push(Math.max(-1, Math.min(1, sample)));
      this.position += this.ratio;
      if (this.output.length === 320) this.flush();
    }
    const consumed = Math.floor(this.position);
    if (consumed > 0) {
      this.samples.splice(0, consumed);
      this.position -= consumed;
    }
    return true;
  }

  flush() {
    const pcm = new Int16Array(this.output.length);
    for (let index = 0; index < this.output.length; index += 1) {
      const sample = this.output[index];
      pcm[index] = sample < 0 ? Math.round(sample * 32768) : Math.round(sample * 32767);
    }
    this.output = [];
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
  }
}

registerProcessor("octocoder-pcm-processor", OctoCoderPCMProcessor);
