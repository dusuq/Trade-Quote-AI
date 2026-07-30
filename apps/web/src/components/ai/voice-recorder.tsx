"use client";

import * as React from "react";

export type RecorderState = "idle" | "requesting" | "recording" | "recorded" | "denied";

export interface UseVoiceRecorder {
  state: RecorderState;
  audioBlob: Blob | null;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

/**
 * Wraps the browser's native MediaRecorder — no new dependency (M15 web UI
 * spec D3). Both mime types MediaRecorder actually produces (audio/webm on
 * Chrome/Firefox, audio/mp4 on Safari) are already on the backend's
 * SUPPORTED_AUDIO_MIME_TYPES whitelist, verified against the source.
 *
 * Stops every MediaStream track on unmount so a page navigation mid-recording
 * never leaves the microphone hot.
 */
export function useVoiceRecorder(): UseVoiceRecorder {
  const [state, setState] = React.useState<RecorderState>("idle");
  const [audioBlob, setAudioBlob] = React.useState<Blob | null>(null);
  const recorderRef = React.useRef<MediaRecorder | null>(null);
  const streamRef = React.useRef<MediaStream | null>(null);
  const chunksRef = React.useRef<Blob[]>([]);

  const stopTracks = React.useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  React.useEffect(() => stopTracks, [stopTracks]);

  const start = React.useCallback(async () => {
    setState("requesting");
    chunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        setAudioBlob(new Blob(chunksRef.current, { type: recorder.mimeType }));
        setState("recorded");
        stopTracks();
      };
      recorder.start();
      setState("recording");
    } catch {
      setState("denied");
    }
  }, [stopTracks]);

  const stop = React.useCallback(() => {
    recorderRef.current?.stop();
  }, []);

  const reset = React.useCallback(() => {
    setAudioBlob(null);
    setState("idle");
  }, []);

  return { state, audioBlob, start, stop, reset };
}
