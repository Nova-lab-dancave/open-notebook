import apiClient from './client'

export interface MeetingAction { text: string; owner: string; due: string; evidence: string; done: boolean }
export interface Meeting {
  id: string; revision: number; title: string; status: 'recording' | 'review' | 'approved'
  capture_mode: 'microphone' | 'shared'; transcript: string; summary: string
  actions: MeetingAction[]; total_chunks: number; missing_chunks: number[]
  interrupted: boolean; summary_status: string; summary_error: string; note_id: string
}
export type MeetingEdit = Pick<Meeting, 'title' | 'summary' | 'actions' | 'transcript' | 'revision'>
const base = (notebook: string) => `/notebooks/${encodeURIComponent(notebook)}/meetings`
const item = (notebook: string, meeting: string) => `${base(notebook)}/${encodeURIComponent(meeting)}`
export const meetingsApi = {
  list: async (notebook: string) => (await apiClient.get<Meeting[]>(base(notebook))).data,
  start: async (notebook: string, title: string, shared: boolean) => (
    await apiClient.post<Meeting>(base(notebook), { title, capture_mode: shared ? 'shared' : 'microphone' })
  ).data,
  chunk: async (notebook: string, meeting: string, sequence: number, audio: Blob) => {
    const body = new FormData()
    body.append('audio', audio, 'chunk.wav')
    return apiClient.post(`${item(notebook, meeting)}/chunks/${sequence}`, body, { timeout: 120000 })
  },
  finish: async (notebook: string, meeting: string, total: number, interrupted = false) => (
    await apiClient.post<Meeting>(`${item(notebook, meeting)}/finish`, { total_chunks: total, interrupted })
  ).data,
  summarize: async (notebook: string, meeting: string) => apiClient.post(`${item(notebook, meeting)}/summarize`),
  edit: async (notebook: string, meeting: string, data: MeetingEdit) => apiClient.patch(`${item(notebook, meeting)}`, data),
  approve: async (notebook: string, meeting: string) => apiClient.post(`${item(notebook, meeting)}/approve`),
  discard: async (notebook: string, meeting: string) => apiClient.delete(item(notebook, meeting)),
}
