import { useTranslation } from 'react-i18next'

import type { Video } from '../concepts/types'

const WATCH_URL = 'https://www.youtube.com/watch?v='

// Los dos videos de la ficha. Lo que llega de YouTube es dato no confiable (el servidor ya lo
// validó): el título y el canal se pintan como texto y el enlace se construye aquí solo con el id.
export default function VideoCards({ videos }: { videos: Video[] }) {
  const { t } = useTranslation()

  return (
    <section className="ficha-section">
      <h2>{t('concept.videos.title')}</h2>
      {videos.length === 0 ? (
        <p className="muted">{t('concept.videos.none')}</p>
      ) : (
        <ul className="videos">
          {videos.map((video) => (
            <li key={video.youtube_id}>
              <a
                className="video-card"
                href={WATCH_URL + encodeURIComponent(video.youtube_id)}
                target="_blank"
                rel="noopener"
              >
                <img className="video-thumb" src={video.thumbnail_url} alt="" loading="lazy" referrerPolicy="no-referrer" />
                <span className="video-title">{video.title}</span>
                {video.channel ? <span className="video-channel">{video.channel}</span> : null}
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
