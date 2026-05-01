# Code Review Report — May 1, 2026
**Author:** Pavel Katurov

---

## 1. Backend Overview

First of all, great job on the backend implementation! The architecture is solid, and your use of **LangGraph** for managing the agent's state machine is a very professional choice. The separation of concerns between `agent.py`, `executor.py`, and `prompts.py` makes the logic easy to follow and maintain.

### Scalability Note
I want to highlight one architectural detail regarding **scalability**. Currently, the session state is managed in-memory using a dictionary in `SessionStore`. This means that if we were to deploy multiple instances of the backend (e.g., behind a load balancer), a user's request might hit a different instance that doesn't have their session history. 

It is important to keep this in mind: for a production-ready, horizontally scalable system, we would typically move this state to an external store like **Redis**. However, since this application is a **prototype**, this in-memory approach is perfectly acceptable and keeps the development cycle fast. There is no need to refactor this now, but it's a key lesson for future high-traffic projects.

---

## 2. Frontend Review

Moving on to the frontend, it’s clear you’ve put a lot of effort into the user experience. Since you are transitioning from backend to full-stack, your progress is impressive!

### Positive Highlights
*   **Clear Component Structure:** Breaking down the UI into `DisputeCard`, `LoyaltyPanel`, and `ResultsTable` shows you understand the modular nature of React.
*   **Intuitive UX:** The `RoleSelector` provides a great onboarding experience, and the typing indicators make the agent feel responsive.
*   **Effective Hook Usage:** You’ve correctly utilized `useEffect`, `useRef`, and `useCallback` to manage the WebSocket lifecycle and auto-scrolling.
*   **Clean Data Presentation:** The tables are well-formatted, and the conditional rendering for different agent roles is implemented very cleanly.

---

## 3. The Importance of Global State Management

The absence of global state management (such as Redux, Zustand, MobX, or at least the built-in React Context) is not an error in itself for tiny projects. However, in this application—which already features complex logic for chat, WebSockets, and roles—it leads to several serious architectural issues.

Here is why this is problematic, using your code as an example:

### 1. Prop Drilling
In the current architecture, all state is stored in the root `App.jsx` component. To pass data or functions to deeply nested components, they have to be "passed through" intermediate components that don't actually need that data.
*   **Code Example:** The functions `onApprove`, `onReject`, and `onCredit` are created in `App.jsx`. They are then passed to the `<Message/>` component. `Message` doesn't need them for its own logic; it takes them solely to pass them further down to `<DisputeCard/>` and `<LoyaltyPanel/>`.
*   **The Downside:** If the hierarchy becomes deeper (e.g., if `DisputeCardActions` is introduced), you will have to drill these functions through 4–5 layers. This significantly clutters the code of intermediate components.

### 2. "God Component"
Since there is no global store, `App.jsx` is forced to take on all responsibility. Currently, it simultaneously:
*   Manages the WebSocket connection (connecting, reconnecting, sending messages).
*   Stores the entire array of chat messages (`messages`).
*   Stores the state of the input field (`input`), selected role (`role`), network status (`connected`), and uploaded files (`receipt`).
*   Contains the business logic (button handlers like `handleApprove`, `handleCredit`, etc.).
*   **The Downside:** The `App.jsx` file already exceeds 300 lines. As new features are added (e.g., authorization, session history, user settings), it will turn into an unreadable monolith of thousands of lines that will be dangerous to touch and impossible to maintain.

### 3. Performance Issues (Unnecessary Re-renders)
When all state resides in the root component, any change—no matter how small—triggers a re-render of the entire application (unless memoization like `React.memo` is used, which is absent in this project).
*   **Code Example:** When a user types in the input field, the `input` state updates (`setInput(e.target.value)`). Because `input` lives in `App.jsx`, React re-renders the entire message list, all result tables, the header, etc., with every single keystroke.
*   **The Downside:** The interface is lightweight for now, but if the chat contains 100 messages with heavy tables (`ResultsTable`), the UI will start to noticeably "lag" during text entry.

### 4. Difficulty in Testing and Reusability
*   If you wanted to move the chat logic into a separate widget (e.g., to embed it on a different page), you would have to extract a chunk of logic out of `App.jsx` along with its state.
*   Testing the WebSocket logic independently of the UI is currently nearly impossible because it is tightly coupled to the `App` component's lifecycle (via `useEffect` and `useRef`).

### How to Fix This (Recommendation):
Using modern, lightweight state managers (e.g., **Zustand** or a **React Context + useReducer** hookup) would allow you to:
1.  Move all WebSocket logic and the message array into a separate **store**.
2.  Allow components (e.g., `DisputeCard` or `MessageInput`) to subscribe **only** to the specific data and functions they need directly from the store, bypassing parent components.
3.  Offload `App.jsx`, leaving it only with the task of basic **Layout** composition.

---

## 4. Recommendations for Frontend Refactoring

### A. State Management & Logic
*   **Implement a Store:** Use **Zustand** or **React Context** to manage the chat history and WebSocket connection.
*   **Logic Isolation:** Move the WebSocket event handlers into a custom hook (e.g., `useChatSocket`) or directly into the store. This decouples the communication logic from the rendering logic.

### B. Component Decomposition
*   **Split the App:** Break `App.jsx` into smaller, focused components:
    *   `<ChatHeader />`
    *   `<MessageList />` (with its own scrolling logic)
    *   `<MessageInput />` (managing its own local text state)
*   **Isolate Input State:** Move the `input` state from `App.jsx` into a standalone `<MessageInput />` component. This will prevent the entire message list from re-rendering as the user types.

### C. Robustness & DX (Developer Experience)
*   **WebSocket Reconnection:** Add a "retry" mechanism for the WebSocket connection. If the server drops, the client should automatically attempt to reconnect with an exponential backoff.
*   **Type Safety:** Consider migrating to **TypeScript**. Given the complexity of the data coming from the LLM (various flags, row formats, etc.), TypeScript will help you catch errors early and provide much better autocomplete in your IDE.
*   **Consistent Styling:** While the inline styles work for a prototype, as the project grows, consider using **CSS Modules** or **Tailwind CSS** to keep your components dry (DRY - Don't Repeat Yourself) and your styling consistent.

---

Great work so far, team! This refactoring stage is a perfect opportunity to level up your frontend skills.