# Strategic Memoization

React is fast by default. Over-memoizing (`useMemo`, `useCallback`) can sometimes hurt performance more than it helps due to the cost of checking dependencies and allocating memory for the memoized functions/values.

## Why it matters
- **Too little:** Expensive calculations block the main thread.
- **Too much:** Code becomes harder to read (`useCallback` hell) and the overhead of memoization outweighs the re-render cost of simple components.

## Incorrect
Memoizing everything blindly.

```tsx
// Incorrect: Primitive values and simple objects don't need memoization
const value = useMemo(() => 42, []);
const style = useMemo(() => ({ color: 'red' }), []);

// Incorrect: Inline functions on lightweight HTML elements are fine
const handleClick = useCallback(() => {
  console.log('clicked');
}, []);

return <button onClick={handleClick}>Click me</button>;
```

## Correct
Memoize only when beneficial.

### 1. Referential Equality for Dependencies
When a value/function is used in a `useEffect` dependency array, stability matters.

```tsx
const params = useMemo(() => ({ id: userId }), [userId]);

useEffect(() => {
  api.fetch(params);
}, [params]); // params must be stable to avoid infinite loops
```

### 2. Expensive Calculations
Heavy synchronous work (e.g., filtering a 5,000 item list).

```tsx
const sortedList = useMemo(() => {
  return largeArray.filter(item => item.active).sort((a, b) => a.value - b.value);
}, [largeArray]);
```

### 3. Passing to Optimized Children (`React.memo`)
If a child component is wrapped in `React.memo`, passing a new function reference every render will break the optimization.

```tsx
const HandleChange = useCallback((val) => {
  setValue(val);
}, []);

// HeavyComponent is wrapped in React.memo, so it needs stable props
return <HeavyComponent onParamChange={HandleChange} />;
```
