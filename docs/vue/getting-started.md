# Vue.js Integration - Getting Started

Learn how to integrate Vue-FastEdgy with your Vue.js application to connect seamlessly with your FastEdgy backend.

## Prerequisites

- Vue 3.0+
- Node.js 22.0+
- NPM or Yarn package manager
- A FastEdgy backend application running

## Installation

Vue-FastEdgy is available as an NPM package from GitHub. Install it using your preferred package manager:

### Using NPM

```bash
npm install git+ssh://git@github.com:krafterio/vue-fastedgy.git#main
```

### Using Yarn

```bash
yarn add git+ssh://git@github.com:krafterio/vue-fastedgy.git#main
```

### Using PNPM

```bash
pnpm add git+ssh://git@github.com:krafterio/vue-fastedgy.git#main
```

## Basic Setup

### 1. Create your Vue application

If you don't have a Vue application yet, create one using Vue CLI or Vite:

```bash
# Using Vite (recommended)
npm create vue@latest my-fastedgy-app
cd my-fastedgy-app
npm install

# Using Vue CLI
vue create my-fastedgy-app
cd my-fastedgy-app
```

### 2. Set up environment variables

Create a `.env` file in your project root:

```bash
# .env
BASE_URL=http://localhost:8000/api
```

### 3. Initialize Vue-FastEdgy in your main.js

**`src/main.js`:**
```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createFetcher } from 'vue-fastedgy'
import App from './App.vue'

const app = createApp(App)
const pinia = createPinia()

// Create fetcher (uses BASE_URL environment variable automatically)
const fetcher = createFetcher()

// Use Pinia for state management
app.use(pinia)

// Use Vue-FastEdgy fetcher
app.use(fetcher)

app.mount('#app')
```

## What's Next?

Your Vue-FastEdgy setup is complete! Continue with basic usage examples:

[Basic Usage](basic-usage.md){ .md-button .md-button--primary }
