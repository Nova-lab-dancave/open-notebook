import { describe, expect, it } from 'vitest'

import nextConfig, { FRAME_SRC_POLICY } from '../../next.config'

// Generated explainers run scripts in a sandboxed blob: iframe. Their own CSP
// blocks subresource requests, but only this app-wide frame-src stops them from
// navigating the frame to an outside URL to send page text away (ADR-015).
describe('app frame-src policy', () => {
  it('only allows blob: frames and the YouTube embed', () => {
    const sources = FRAME_SRC_POLICY.replace(/^frame-src\s+/, '').split(/\s+/)
    expect(sources).toEqual(['blob:', 'https://www.youtube.com', 'https://www.youtube-nocookie.com'])
    expect(FRAME_SRC_POLICY).not.toMatch(/\*|https:(\s|$)|data:/)
  })

  it('is sent on every route', async () => {
    const rules = (await nextConfig.headers?.()) ?? []
    const rule = rules.find((r) => r.source === '/:path*')
    expect(rule?.headers).toContainEqual({ key: 'Content-Security-Policy', value: FRAME_SRC_POLICY })
  })
})
