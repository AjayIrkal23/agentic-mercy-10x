# Frontend API Module Template

Use this reference only when the task already routed into `frontend-response-handling`.

## Purpose

Provide a reusable pattern for:

- explicit success-envelope parsing
- backend-driven list query params
- normalized error throwing

## Example

```ts
import { apiClient, ApiError } from "@/api/client"
import type { ApiResponse, PaginatedResponse } from "@/api/types"

const ENDPOINT = "/<domain>/<resource>"

type ListApiEnvelope<T> = ApiResponse<T[]> & {
  meta?: {
    page: number
    limit: number
    total: number
    totalPages: number
    sortBy?: string
    sortOrder?: "asc" | "desc"
  }
}

function removeEmptyValues(params?: Record<string, unknown>): Record<string, unknown> {
  if (!params) return {}

  return Object.entries(params).reduce<Record<string, unknown>>((acc, [key, value]) => {
    if (value === undefined || value === null || value === "") return acc
    acc[key] = value
    return acc
  }, {})
}

export async function getResourceListApi(
  params: ResourceListQueryParams
): Promise<PaginatedResponse<Resource>> {
  try {
    const res = await apiClient.get<ListApiEnvelope<Resource>>(ENDPOINT, {
      params: removeEmptyValues(params as Record<string, unknown>),
    })

    return {
      data: res.data.data,
      meta: res.data.meta,
    }
  } catch (error) {
    throw ApiError.fromAxiosError(error as never)
  }
}
```

## Rules

- Parse the backend envelope in the API layer.
- Return typed frontend data, not raw transport responses.
- Strip empty params before sending list queries.
- Throw one normalized error type from the API layer.
- Keep transport details out of the component layer.
