# Voice OS Bharat

A multilingual AI voice assistant built for Bharat. Supports 10 Indian languages including Hindi, English, Tamil, Bengali, Telugu, Kannada, Malayalam, Marathi, Punjabi, and Gujarati.

## Tech Stack

- **React 18** with TypeScript
- **Vite** for fast development and builds
- **Tailwind CSS** for styling
- **React Router** for navigation

## Getting Started

### Prerequisites

- [Node.js](https://nodejs.org/) v18 or higher
- npm (comes with Node.js)

### Installation

```bash
# Navigate to the frontend directory
cd frontend/harmony-hub-main

# Install dependencies
npm install
```

### Development

```bash
npm run dev
```

Open [http://localhost:8080](http://localhost:8080) in your browser.

### Production Build

```bash
npm run build
npm run preview
```

## Project Structure

```
src/
├── components/         # Reusable UI components
│   ├── result/         # Result page components
│   ├── BackButton.tsx
│   ├── Footer.tsx
│   ├── LanguageSelector.tsx
│   ├── MicButton.tsx
│   ├── Navbar.tsx
│   └── VoiceInteraction.tsx
├── pages/              # Route-level page components
│   ├── Index.tsx
│   ├── NotFound.tsx
│   └── ResultPage.tsx
├── App.tsx             # Root component with routing
├── index.css           # Global styles and Tailwind config
├── main.tsx            # Application entry point
└── vite-env.d.ts       # Vite type declarations
```
