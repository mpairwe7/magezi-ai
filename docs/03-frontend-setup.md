# 3. Frontend Setup — Magezi AI

## Components (12)

| Component | Purpose |
|-----------|---------|
| ConversationRail | Conversation history sidebar (grouped by time) |
| NavSidebar | 3-level mobile nav (top bar + sidebar + bottom nav) |
| SubjectSelector | Physics/Chemistry/Biology/Maths picker |
| AuthModal | Login/signup modal |
| ChatInput | Message input + voice recording |
| ChatMessage | Message with formulas, citations |
| StarterPrompts | Subject-specific prompt suggestions |
| SettingsPanel | Language, theme, API key settings |
| Icons | SVG icon library |

## State Management (Zustand)

- **useChatStore** (23KB): multi-workspace (anonymous + account), conversation CRUD, drafts, turns
- **useAuthStore** (1.2KB): user profile, JWT token, credits

## Design System

- Dark theme: forest green (#040a06) + gold (#eab308) + earth (#d97706)
- Subject colors: Physics (blue), Chemistry (green), Biology (amber), Maths (purple)
- Glassmorphism with backdrop blur
- 960px desktop breakpoint
