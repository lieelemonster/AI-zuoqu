import { useEffect, useState } from 'react';
import { getHealth } from './api/health';

type Connection = 'checking' | 'connected' | 'failed';

export default function App() {
  const [connection, setConnection] = useState<Connection>('checking');

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 5000);
    getHealth(controller.signal)
      .then(() => { if (active) setConnection('connected'); })
      .catch(() => {
        if (active) setConnection('failed');
      });
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  const status = {
    checking: '正在检查后端连接…',
    connected: '后端已连接 · /api/health 返回 ok',
    failed: '后端未连接，请启动后端后刷新页面。',
  }[connection];

  return (
    <main>
      <p className="eyebrow">本地开发 · 基础脚手架</p>
      <h1>AI 写词与作曲</h1>
      <p className="intro">React + TypeScript + FastAPI 项目已启动。</p>
      <section className="status" aria-label="服务状态">
        <span className={`dot ${connection}`} aria-hidden="true" />
        <p role="status">{status}</p>
      </section>
      <section className="placeholder">
        <h2>创作功能将在后续任务中实现</h2>
        <p>当前仅验证页面与后端连接，尚未接入歌词生成、作曲和音频下载。</p>
      </section>
    </main>
  );
}
