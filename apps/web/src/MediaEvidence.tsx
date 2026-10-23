import { useEffect, useRef, useState } from 'react';

type Event = { status: string; metric: string; value?: number; experiment_time_s: number;
  video_time_s: number; frame_index: number | null; frame_timestamp_s?: number; offset_error_s?: number };
type Report = { video: { episode_id: string; camera: string; source_sha256: string; frame_count: number;
  duration_s: number; offset_s: number; variable_frame_rate: boolean;
  suspected_gap_frame_indices: number[]; fps_mismatch: boolean }; events: Event[] };

export function MediaEvidence() {
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState('');
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [durationMismatch, setDurationMismatch] = useState(false);
  const [hashMatch, setHashMatch] = useState<boolean | null>(null);
  const player = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (!videoFile) { setVideoUrl(null); return; }
    const url = URL.createObjectURL(videoFile);
    setVideoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [videoFile]);
  useEffect(() => {
    let active = true;
    setHashMatch(null);
    if (!videoFile || !report || videoFile.size > 128 * 1024 * 1024) return;
    void videoFile.arrayBuffer().then(buffer => crypto.subtle.digest('SHA-256', buffer)).then(bytes => {
      const actual = Array.from(new Uint8Array(bytes)).map(value => value.toString(16).padStart(2, '0')).join('');
      if (active) setHashMatch(actual === report.video.source_sha256);
    }).catch(() => { if (active) setHashMatch(false); });
    return () => { active = false; };
  }, [videoFile, report]);
  async function readReport(file: File) {
    setError('');
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!parsed || typeof parsed !== 'object' || !('video' in parsed) || !('events' in parsed)) throw new Error('报告缺少 video/events');
      const candidate = parsed as Report;
      if (!candidate.video || typeof candidate.video.episode_id !== 'string' ||
          !Array.isArray(candidate.events) || candidate.events.some(event =>
            typeof event.metric !== 'string' || typeof event.video_time_s !== 'number' ||
            (event.frame_index !== null && typeof event.frame_index !== 'number'))) throw new Error('报告字段无效');
      setReport(candidate); setDurationMismatch(false);
    } catch (cause) { setReport(null); setError(String(cause)); }
  }
  function seek(event: Event) {
    if (!player.current || hashMatch !== true || event.status !== 'located' || event.frame_index === null) return;
    player.current.currentTime = event.frame_timestamp_s ?? event.video_time_s;
    void player.current.play();
  }
  return <section className="media-evidence" aria-label="外部结果视频对照">
    <p>选择原始视频和本地时序报告，点击指标事件定位到对应帧。仅在本机读取。</p>
    <label>视频 <input type="file" accept="video/*" onChange={event => setVideoFile(event.target.files?.[0] ?? null)} /></label>
    <label>时序报告 JSON <input type="file" accept="application/json,.json" onChange={event => {
      const file = event.target.files?.[0]; if (file) void readReport(file);
    }} /></label>
    {error && <p role="alert">{error}</p>}
    {videoUrl && <video ref={player} controls src={videoUrl} onLoadedMetadata={() => {
      if (report && player.current) setDurationMismatch(Math.abs(player.current.duration - report.video.duration_s) > 0.2);
    }} aria-label="外部实验视频" />}
    {report && <div>
      <p>Episode：{report.video.episode_id} · 相机：{report.video.camera} · 帧数：{report.video.frame_count} · 偏移：{report.video.offset_s}s</p>
      <p>视频 SHA-256：<code>{report.video.source_sha256}</code></p>
      <p role={hashMatch === false ? 'alert' : undefined}>文件校验：{hashMatch === true ? '与报告一致' : hashMatch === false ? '不一致，已禁用定位' : '待验证；超过 128 MiB 的视频暂不在界面校验'}</p>
      {(report.video.variable_frame_rate || report.video.fps_mismatch || report.video.suspected_gap_frame_indices.length > 0 || durationMismatch) &&
        <p role="alert">时序注意：{report.video.variable_frame_rate ? '变帧率；' : ''}{report.video.fps_mismatch ? '声明帧率不符；' : ''}
          {report.video.suspected_gap_frame_indices.length ? `疑似缺帧 ${report.video.suspected_gap_frame_indices.join(',')}；` : ''}
          {durationMismatch ? '视频时长与报告不符；' : ''}</p>}
      <ul>{report.events.map((item, index) => <li key={index}><button disabled={!videoUrl || hashMatch !== true || item.status !== 'located'}
        onClick={() => seek(item)}>{item.metric} · t={item.experiment_time_s}s → 视频 {item.video_time_s}s
          {item.frame_index === null ? '（超出视频）' : ` · 帧 ${item.frame_index}`}</button></li>)}</ul>
      <p>视频不提供扭矩或能耗测量；机械原因需要其它证据复核。</p>
    </div>}
  </section>;
}
