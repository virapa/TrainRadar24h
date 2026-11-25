import { useCallback, useEffect, useState } from 'react'
import { deleteFavorite, listFavorites, putFavorite } from '../api/client'
import type { Avisos, Favorite, FavoriteKind } from '../api/types'

/** Favoritos de este dispositivo. Tras cada cambio se relee la lista del servidor. */
export function useFavorites() {
  const [list, setList] = useState<Favorite[]>([])

  const reload = useCallback(async () => {
    try {
      setList(await listFavorites())
    } catch {
      // Sin conexión: se conserva la lista que hubiera.
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const has = useCallback(
    (tipo: FavoriteKind, ref: string) => list.some((f) => f.tipo === tipo && f.ref === ref),
    [list],
  )

  const toggle = useCallback(
    async (tipo: FavoriteKind, ref: string) => {
      try {
        if (has(tipo, ref)) await deleteFavorite(tipo, ref)
        else await putFavorite({ tipo, ref })
      } finally {
        await reload()
      }
    },
    [has, reload],
  )

  const setAvisos = useCallback(
    async (fav: Favorite, avisos: Avisos) => {
      try {
        await putFavorite({ tipo: fav.tipo, ref: fav.ref, avisos })
      } finally {
        await reload()
      }
    },
    [reload],
  )

  return { list, has, toggle, setAvisos }
}
