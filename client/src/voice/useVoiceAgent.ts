import { useCallback, useEffect, useRef, useState } from "react";
import type { RefObject } from "react";
import type { OctoCoderSocket } from "../socket";
import type { ServerMessage, VoiceAudioMetadata, VoicePhase, VoiceSettings } from "../types";
import { ContinuousVoiceDetector } from "./continuous";
import { VoicePlaybackQueue } from "./playback";
import { PCMStreamRecorder } from "./recorder";
import { isNoSpeechVoiceError, PCMActivityMeter, VoiceSessionState } from "./voiceState";

type VoiceAgentOptions = {
  socketRef: RefObject<OctoCoderSocket | null>;
  config: VoiceSettings | null;
  agentBusy: boolean;
  onTranscript: (text: string) => void;
  onAutoSubmitted: (text: string) => void;
  onError: (message: string) => void;
};

const MAX_PENDING_PCM_BYTES = 1024 * 1024;

function requestId(): string {
  return `voice_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
}

function microphoneError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "麦克风权限被拒绝，请在系统设置中允许后重试。";
    if (error.name === "NotFoundError") return "没有检测到麦克风。";
    if (error.name === "NotReadableError") return "麦克风正在被其他应用占用。";
  }
  return error instanceof Error ? error.message : "无法启动麦克风。";
}

export function useVoiceAgent({
  socketRef,
  config,
  agentBusy,
  onTranscript,
  onAutoSubmitted,
  onError
}: VoiceAgentOptions) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [caption, setCaption] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [pendingTranscriptRequestId, setPendingTranscriptRequestId] = useState("");
  const [continuousEnabled, setContinuousEnabled] = useState(false);
  const sessionRef = useRef(new VoiceSessionState());
  const knownRequestsRef = useRef(new Set<string>());
  const latestRequestRef = useRef("");
  const pendingFramesRef = useRef<ArrayBuffer[]>([]);
  const pendingBytesRef = useRef(0);
  const finishRequestedRef = useRef(false);
  const manualActivityRef = useRef(new PCMActivityMeter());
  const manualPreFramesRef = useRef<ArrayBuffer[]>([]);
  const manualPreBytesRef = useRef(0);
  const manualStartingRef = useRef(false);
  const manualStoppingRef = useRef(false);
  const manualReleaseRequestedRef = useRef(false);
  const manualGenerationRef = useRef(0);
  const elapsedTimerRef = useRef(0);
  const recorderRef = useRef(new PCMStreamRecorder());
  const detectorRef = useRef(new ContinuousVoiceDetector());
  const callbacksRef = useRef({ onTranscript, onAutoSubmitted, onError });
  callbacksRef.current = { onTranscript, onAutoSubmitted, onError };

  const playbackRef = useRef<VoicePlaybackQueue | null>(null);
  if (!playbackRef.current) {
    playbackRef.current = new VoicePlaybackQueue(
      (playing) => {
        if (playing) setPhase("speaking");
      },
      (message) => callbacksRef.current.onError(message)
    );
  }

  const clearElapsedTimer = useCallback(() => {
    if (elapsedTimerRef.current) window.clearInterval(elapsedTimerRef.current);
    elapsedTimerRef.current = 0;
  }, []);

  const startElapsedTimer = useCallback(() => {
    clearElapsedTimer();
    setElapsedSeconds(0);
    elapsedTimerRef.current = window.setInterval(
      () => setElapsedSeconds((value) => value + 1),
      1000
    );
  }, [clearElapsedTimer]);

  const resetPendingFrames = useCallback(() => {
    pendingFramesRef.current = [];
    pendingBytesRef.current = 0;
  }, []);

  const resetManualCapture = useCallback(() => {
    manualActivityRef.current.reset();
    manualPreFramesRef.current = [];
    manualPreBytesRef.current = 0;
    manualStartingRef.current = false;
    manualStoppingRef.current = false;
    manualReleaseRequestedRef.current = false;
  }, []);

  const fail = useCallback((message: string) => {
    clearElapsedTimer();
    setPhase("error");
    callbacksRef.current.onError(message);
  }, [clearElapsedTimer]);

  const interruptPlayback = useCallback(() => {
    if (!playbackRef.current?.isPlaying) return;
    playbackRef.current.stop();
    socketRef.current?.send({
      type: "voice_playback_interrupt",
      data: { requestId: latestRequestRef.current }
    });
  }, [socketRef]);

  const sendFrame = useCallback((frame: ArrayBuffer) => {
    const session = sessionRef.current;
    if (!session.requestId) return;
    if (session.phase !== "recording") {
      if (pendingBytesRef.current + frame.byteLength > MAX_PENDING_PCM_BYTES) {
        fail("实时音频缓冲区已满，请重试。");
        return;
      }
      pendingFramesRef.current.push(frame);
      pendingBytesRef.current += frame.byteLength;
      return;
    }
    const sequence = session.nextFrameSequence();
    if (!socketRef.current?.sendVoiceFrame(session.requestId, sequence, frame)) {
      fail("后端连接已断开，音频帧未发送。");
    }
  }, [fail, socketRef]);

  const acceptManualFrame = useCallback((frame: ArrayBuffer) => {
    manualActivityRef.current.addFrame(frame);
    if (!sessionRef.current.requestId) {
      if (manualPreBytesRef.current + frame.byteLength > MAX_PENDING_PCM_BYTES) {
        fail("实时音频缓冲区已满，请重试。");
        return;
      }
      manualPreFramesRef.current.push(frame);
      manualPreBytesRef.current += frame.byteLength;
      return;
    }
    sendFrame(frame);
  }, [fail, sendFrame]);

  const flushPendingFrames = useCallback(() => {
    const frames = pendingFramesRef.current;
    pendingFramesRef.current = [];
    pendingBytesRef.current = 0;
    for (const frame of frames) sendFrame(frame);
  }, [sendFrame]);

  const finishStream = useCallback(() => {
    const session = sessionRef.current;
    finishRequestedRef.current = true;
    clearElapsedTimer();
    if (session.phase !== "recording" || !session.finish()) return;
    setPhase("transcribing");
    socketRef.current?.send({
      type: "voice_stream_finish",
      data: { requestId: session.requestId }
    });
  }, [clearElapsedTimer, socketRef]);

  const cancelStream = useCallback((returnToListening = false) => {
    const session = sessionRef.current;
    const id = session.requestId;
    recorderRef.current.cancel();
    clearElapsedTimer();
    resetPendingFrames();
    manualGenerationRef.current += 1;
    resetManualCapture();
    finishRequestedRef.current = false;
    if (id) {
      socketRef.current?.send({ type: "voice_stream_cancel", data: { requestId: id } });
      knownRequestsRef.current.delete(id);
    }
    session.reset(returnToListening ? "listening" : "idle");
    setCaption("");
    setElapsedSeconds(0);
    setPhase(returnToListening ? "listening" : "idle");
  }, [clearElapsedTimer, resetManualCapture, resetPendingFrames, socketRef]);

  const beginStream = useCallback((mode: "hold" | "continuous", preSpeech: ArrayBuffer[] = []) => {
    const session = sessionRef.current;
    if (session.requestId) return false;
    const id = requestId();
    session.begin(id, mode);
    knownRequestsRef.current.add(id);
    latestRequestRef.current = id;
    finishRequestedRef.current = false;
    resetPendingFrames();
    for (const frame of preSpeech) sendFrame(frame);
    const sent = socketRef.current?.send({
      type: "voice_stream_start",
      data: {
        requestId: id,
        mode,
        format: "pcm_s16le",
        sampleRate: 16000,
        channels: 1
      }
    });
    if (!sent) {
      session.reset();
      knownRequestsRef.current.delete(id);
      fail("后端尚未连接。");
      return false;
    }
    setCaption("");
    setPhase("connecting");
    startElapsedTimer();
    return true;
  }, [fail, resetPendingFrames, sendFrame, socketRef, startElapsedTimer]);

  const stopRecording = useCallback(async () => {
    manualReleaseRequestedRef.current = true;
    if (manualStartingRef.current || manualStoppingRef.current) return;
    if (sessionRef.current.mode !== "hold" || !sessionRef.current.requestId) return;
    manualStoppingRef.current = true;
    await recorderRef.current.stop().catch(() => undefined);
    manualStoppingRef.current = false;
    if (!manualActivityRef.current.canSubmit()) {
      cancelStream(false);
      callbacksRef.current.onError("未检测到清晰语音，请按住麦克风后再说话。");
      return;
    }
    finishStream();
  }, [cancelStream, finishStream]);

  const startRecording = useCallback(async () => {
    if (!config?.enabled || !config.streamingConfigured) {
      fail("请先在设置中配置阿里云百炼实时语音识别。");
      return;
    }
    if (agentBusy) return;
    interruptPlayback();
    recorderRef.current.cancel();
    const generation = manualGenerationRef.current + 1;
    manualGenerationRef.current = generation;
    resetManualCapture();
    manualStartingRef.current = true;
    setPendingTranscriptRequestId("");
    setPhase("requesting_permission");
    try {
      await recorderRef.current.start(acceptManualFrame, () => void stopRecording());
      if (generation !== manualGenerationRef.current) {
        recorderRef.current.cancel();
        return;
      }
      manualStartingRef.current = false;
      if (manualReleaseRequestedRef.current) {
        recorderRef.current.cancel();
        resetManualCapture();
        setPhase("idle");
        callbacksRef.current.onError("录音时间太短，请按住麦克风后再说话。");
        return;
      }
      const preFrames = manualPreFramesRef.current;
      manualPreFramesRef.current = [];
      manualPreBytesRef.current = 0;
      const started = beginStream("hold", preFrames);
      if (!started) recorderRef.current.cancel();
    } catch (error) {
      if (generation !== manualGenerationRef.current) return;
      cancelStream(false);
      fail(microphoneError(error));
    }
  }, [acceptManualFrame, agentBusy, beginStream, cancelStream, config, fail, interruptPlayback, resetManualCapture, stopRecording]);

  const stopContinuous = useCallback(() => {
    detectorRef.current.destroy();
    setContinuousEnabled(false);
    cancelStream(false);
  }, [cancelStream]);

  const startContinuous = useCallback(async () => {
    if (!config?.enabled || !config.streamingConfigured) {
      fail("请先配置可用的阿里云百炼实时 ASR Profile。");
      return;
    }
    setPhase("requesting_permission");
    try {
      await detectorRef.current.start(config.continuousSilenceMs, {
        onSpeechStart: (preSpeech) => {
          interruptPlayback();
          beginStream("continuous", preSpeech);
        },
        onSpeechFrame: sendFrame,
        onSpeechEnd: finishStream,
        onMisfire: () => cancelStream(true)
      });
      setContinuousEnabled(true);
      if (!sessionRef.current.requestId) setPhase("listening");
    } catch (error) {
      detectorRef.current.destroy();
      setContinuousEnabled(false);
      fail(microphoneError(error));
    }
  }, [beginStream, cancelStream, config, fail, finishStream, interruptPlayback, sendFrame]);

  const toggleContinuous = useCallback(() => {
    if (continuousEnabled) stopContinuous();
    else void startContinuous();
  }, [continuousEnabled, startContinuous, stopContinuous]);

  const stopPlayback = useCallback(() => {
    playbackRef.current?.stop();
    socketRef.current?.send({
      type: "voice_playback_interrupt",
      data: { requestId: latestRequestRef.current }
    });
    setPhase(continuousEnabled ? "listening" : "idle");
  }, [continuousEnabled, socketRef]);

  const handleServerMessage = useCallback((message: ServerMessage) => {
    const session = sessionRef.current;
    if (message.type === "voice_stream_ready") {
      if (message.data.requestId !== session.requestId || !session.ready()) return;
      setPhase("recording");
      flushPendingFrames();
      if (finishRequestedRef.current) finishStream();
      return;
    }
    if (message.type === "voice_transcript_partial") {
      if (session.partial(message.data.requestId, message.data.text, message.data.revision)) {
        setCaption(message.data.text);
      }
      return;
    }
    if (message.type === "voice_error") {
      if (message.data.requestId && !knownRequestsRef.current.has(message.data.requestId)) return;
      if (message.data.requestId === session.requestId) {
        recorderRef.current.cancel();
        resetPendingFrames();
        session.reset(continuousEnabled ? "listening" : "idle");
      }
      knownRequestsRef.current.delete(message.data.requestId);
      const noSpeech = isNoSpeechVoiceError(message.data.message);
      if (continuousEnabled && noSpeech) {
        clearElapsedTimer();
        setCaption("");
        setPhase("listening");
        return;
      }
      fail(noSpeech ? "未检测到清晰语音，请重试。" : message.data.message);
      if (continuousEnabled) window.setTimeout(() => setPhase("listening"), 600);
      return;
    }
    if (message.type === "voice_transcript") {
      if (!session.transcript(message.data.requestId, message.data.text)) return;
      clearElapsedTimer();
      setElapsedSeconds(0);
      setCaption(message.data.text);
      if (message.data.submitted) {
        setPendingTranscriptRequestId("");
        callbacksRef.current.onAutoSubmitted(message.data.text);
      } else {
        setPendingTranscriptRequestId(message.data.requestId);
        callbacksRef.current.onTranscript(message.data.text);
      }
      session.reset(continuousEnabled ? "listening" : "idle");
      finishRequestedRef.current = false;
      resetPendingFrames();
      if (continuousEnabled) setPhase("listening");
      return;
    }
    if (message.type === "voice_status") {
      if (!knownRequestsRef.current.has(message.data.requestId)) return;
      if (message.data.phase === "idle") {
        knownRequestsRef.current.delete(message.data.requestId);
        if (!playbackRef.current?.isPlaying) setPhase(continuousEnabled ? "listening" : "idle");
      } else {
        setPhase(message.data.phase);
      }
      return;
    }
    if (message.type === "voice_audio_cancel") {
      playbackRef.current?.stop();
    }
  }, [clearElapsedTimer, continuousEnabled, fail, finishStream, flushPendingFrames, resetPendingFrames]);

  const handleVoiceAudio = useCallback((metadata: VoiceAudioMetadata, data: ArrayBuffer) => {
    if (!knownRequestsRef.current.has(metadata.requestId)) return;
    playbackRef.current?.enqueue(metadata, data);
  }, []);

  const handleDisconnect = useCallback(() => {
    const id = sessionRef.current.requestId;
    if (id) socketRef.current?.send({ type: "voice_stream_cancel", data: { requestId: id } });
    recorderRef.current.cancel();
    detectorRef.current.destroy();
    playbackRef.current?.stop();
    clearElapsedTimer();
    sessionRef.current.reset();
    knownRequestsRef.current.clear();
    latestRequestRef.current = "";
    resetPendingFrames();
    finishRequestedRef.current = false;
    manualGenerationRef.current += 1;
    resetManualCapture();
    setContinuousEnabled(false);
    setPendingTranscriptRequestId("");
    setCaption("");
    setElapsedSeconds(0);
    setPhase("idle");
  }, [clearElapsedTimer, resetManualCapture, resetPendingFrames, socketRef]);

  const markTranscriptSubmitted = useCallback((): string => {
    const id = pendingTranscriptRequestId;
    setPendingTranscriptRequestId("");
    return id;
  }, [pendingTranscriptRequestId]);

  const discardTranscriptOrigin = useCallback(() => setPendingTranscriptRequestId(""), []);

  useEffect(() => {
    if (!config?.enabled) handleDisconnect();
    if (config?.mode !== "continuous" && continuousEnabled) stopContinuous();
  }, [config?.enabled, config?.mode, continuousEnabled, handleDisconnect, stopContinuous]);

  useEffect(() => () => {
    recorderRef.current.dispose();
    detectorRef.current.destroy();
    playbackRef.current?.dispose();
    clearElapsedTimer();
  }, [clearElapsedTimer]);

  return {
    phase,
    caption,
    elapsedSeconds,
    pendingTranscriptRequestId,
    continuousEnabled,
    supported: PCMStreamRecorder.isSupported(),
    startRecording,
    stopRecording,
    cancelRecording: () => cancelStream(continuousEnabled),
    toggleContinuous,
    stopPlayback,
    handleServerMessage,
    handleVoiceAudio,
    handleDisconnect,
    markTranscriptSubmitted,
    discardTranscriptOrigin
  };
}
