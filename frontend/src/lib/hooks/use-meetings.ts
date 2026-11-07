import { useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { meetingsApi } from '@/lib/api/meetings'
import { QUERY_KEYS } from '@/lib/api/query-client'
import { useToast } from './use-toast'
import { useTranslation } from './use-translation'
import { getApiErrorMessage } from '@/lib/utils/error-handler'

export function useMeetings(notebookId: string) {
  const client = useQueryClient()
  const { t } = useTranslation()
  const { toast } = useToast()
  const refresh = useCallback(async () => {
    await client.invalidateQueries({ queryKey: QUERY_KEYS.meetings(notebookId) })
    await client.invalidateQueries({ queryKey: QUERY_KEYS.notes(notebookId) })
  }, [client, notebookId])
  const query = useQuery({
    queryKey: QUERY_KEYS.meetings(notebookId),
    queryFn: () => meetingsApi.list(notebookId),
    retry: false,
    refetchInterval: (q) => q.state.data?.some((m) => m.status === 'recording' || ['new', 'queued', 'running'].includes(m.summary_status)) ? 4000 : false,
  })
  const action = useMutation({
    mutationFn: (operation: () => Promise<unknown>) => operation(),
    retry: false,
    onSuccess: async () => { await refresh(); toast({ title: t('common.success') }) },
    onError: (error) => toast({ title: t('common.error'), description: getApiErrorMessage(error, t), variant: 'destructive' }),
  })
  return { ...query, refresh, action }
}
