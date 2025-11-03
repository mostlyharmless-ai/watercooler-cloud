# Watercooler Landing Page

A production-quality landing page for Watercooler - a shared memory protocol where humans and AI agents collaborate with structure, context, and traceability.

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Animations**: Framer Motion
- **Icons**: Lucide React
- **Fonts**: Inter (sans) + IBM Plex Mono (mono)

## Features

- ✨ Dark, minimalist UI with Watercooler brand tokens
- 🎨 Animated terminal demo showcasing agent collaboration
- 📱 Fully responsive design (mobile-first, 375px+)
- ♿ WCAG AA accessible (keyboard navigation, proper landmarks)
- 🎭 Reduced-motion support for accessibility
- 🚀 SEO optimized (OpenGraph, Twitter cards)
- 📊 Lighthouse score target: ≥95

## Getting Started

### Install dependencies

```bash
pnpm install
```

### Run development server

```bash
pnpm dev
```

Open [http://localhost:5001](http://localhost:5001) in your browser.

### Build for production

```bash
pnpm build
```

### Start production server

```bash
pnpm start
```

## Project Structure

```
/app
  layout.tsx          # Root layout with fonts and SEO
  page.tsx            # Main landing page
  globals.css         # Global styles
  /api/health         # Health check endpoint
  robots.txt          # SEO robots file
  sitemap.xml         # Sitemap
  
/components
  Button.tsx          # Reusable button with variants
  Container.tsx       # Responsive container
  Header.tsx          # Sticky header with blur
  Hero.tsx            # Hero section
  Problem.tsx         # Problem cards
  Solution.tsx        # Solution bullets & diagram
  ComponentsGrid.tsx  # Components showcase
  Quickstart.tsx      # Quickstart code section
  DemoStrip.tsx       # Visual demos
  Community.tsx       # Open-source CTA
  Footer.tsx          # Footer with links
  CodeBlock.tsx       # Code block with copy button
  TerminalAnimated.tsx # Animated terminal
  GraphTeaser.tsx     # SVG graph animation
  Callouts.tsx        # Why Now section
  
/lib
  copy.ts             # All copy content
  seo.ts              # SEO configuration
  utils.ts            # Utility functions
  
/public
  /logos              # SVG logos
  /images             # Graphics
```

## Deployment

### Vercel (Recommended)

```bash
pnpm dlx vercel deploy
```

### Other Platforms

Build the project and deploy the `.next` folder:

```bash
pnpm build
```

## License

MIT

## Links

- GitHub: 
- Discord: 
- Docs: /docs (coming soon)
