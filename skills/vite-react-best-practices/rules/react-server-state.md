# Separation of Server State

Server state (data from an API) behaves differently than Client state (UI interactions). It needs caching, polling, deduplication, and stale-while-revalidate logic.

## Why it matters
Managing server data with `useEffect` and `useState` leads to:
- **Race conditions:** Responses arriving out of order.
- **Waterfalls:** Child components waiting for parents to finish fetching.
- **Complexity:** Manually handling loading/error/success states.

## Incorrect
Manual fetching in `useEffect`.

```tsx
function UserProfile() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/user')
      .then((res) => res.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      });
  }, []); // Only runs once, but what if we need to refetch?

  if (loading) return <div>Loading...</div>;
  return <div>{data.name}</div>;
}
```

## Correct
Use a purpose-built library like **TanStack Query (React Query)** or **SWR**.

```tsx
import { useQuery } from '@tanstack/react-query';

function UserProfile() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['user'],
    queryFn: () => fetch('/api/user').then((res) => res.json())
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error detected</div>;

  return <div>{data.name}</div>;
}
```
