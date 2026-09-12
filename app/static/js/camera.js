export function cameraSupported() {
  return Boolean(navigator.mediaDevices?.getUserMedia);
}

export class CameraController {
  constructor(video, canvas) {
    this.video = video;
    this.canvas = canvas;
    this.stream = null;
    this.facingMode = 'environment';
  }

  async start(facingMode=this.facingMode) {
    if (!cameraSupported()) throw new Error('Camera access is not supported by this browser.');
    this.facingMode = facingMode;
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: {ideal:facingMode},
        width: {ideal:1920},
        height: {ideal:1080},
      },
      audio: false,
    });
    this.video.srcObject = this.stream;
    await this.video.play();
    return this.stream;
  }

  async switchCamera() {
    const next = this.facingMode === 'environment' ? 'user' : 'environment';
    this.stop();
    return this.start(next);
  }

  stop() {
    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }
    this.video.srcObject = null;
  }

  capture({maxWidth=1280, quality=0.78} = {}) {
    if (!this.stream || !this.video.videoWidth) throw new Error('Camera is not ready.');
    const scale = Math.min(1, maxWidth / this.video.videoWidth);
    const width = Math.max(1, Math.round(this.video.videoWidth * scale));
    const height = Math.max(1, Math.round(this.video.videoHeight * scale));
    this.canvas.width = width;
    this.canvas.height = height;
    const ctx = this.canvas.getContext('2d', {alpha:false});
    ctx.drawImage(this.video, 0, 0, width, height);
    return this.canvas.toDataURL('image/jpeg', quality);
  }
}
