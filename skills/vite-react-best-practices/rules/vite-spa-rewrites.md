# Configure Static Host Rewrites for SPA Routing

Vite SPAs differ from Next.js in that they have no server-side routing logic. When a user navigates deeper than `/` (e.g., `/dashboard`), and hits "Refresh", the browser asks the server for `/dashboard`. Without a rewrite rule, the static host returns 404.

## Why it matters
Failing to configure rewrites is the #1 cause of "404 Not Found" errors on page refresh in SPAs. It breaks deep linking, sharing URLs, and user confidence.

## Incorrect
Deploying a Vite app to S3, Netlify, or Nginx without specific SPA configuration.

```nginx
# Nginx default (Incorrect for SPA)
location / {
  root /var/www/html;
  index index.html;
  # Returns 404 if file not found
}
```

## Correct
Configure the host to serve `index.html` for any unknown path, allowing the client-side React Router to handle the URL.

### Nginx
```nginx
location / {
  try_files $uri $uri/ /index.html;
}
```

### Netlify (`netlify.toml`)
```toml
[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

### Vercel (`vercel.json`)
```json
{
  "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }]
}
```

### Firebase (`firebase.json`)
```json
{
  "hosting": {
    "rewrites": [{ "source": "**", "destination": "/index.html" }]
  }
}
```
