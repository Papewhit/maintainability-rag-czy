import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import assert from "node:assert/strict";
import vm from "node:vm";

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, "..", "..", "..");
const frontendDir = join(repoRoot, "frontend");

const readFrontend = (file) => readFileSync(join(frontendDir, file), "utf8");
const readRepo = (file) => readFileSync(join(repoRoot, file), "utf8");

const index = readFrontend("index.html");
const css = readFrontend("style.css");
const script = readFrontend("script.js");
const logo = readFrontend("logo-ragtenance.svg");
const backendSchemas = readRepo("backend/contracts/schemas.py");
const backendApi = readRepo("backend/api.py");
const backendRouterAuth = readRepo("backend/routers/auth.py");
const backendRouterChat = readRepo("backend/routers/chat.py");
const backendRouterSessions = readRepo("backend/routers/sessions.py");
const backendRouterDocuments = readRepo("backend/routers/documents.py");
const backendAgent = readRepo("backend/chat/agent.py");
const backendRagExecution = readRepo("backend/chat/rag_execution.py");
const backendTools = readRepo("backend/chat/tools.py");
const backendRagPipeline = readRepo("backend/rag/pipeline.py");
const backendRagUtils = readRepo("backend/rag/utils.py");
const backendRagRetrieval = readRepo("backend/rag/retrieval.py");

function loadAppOptions() {
  let capturedOptions = null;
  const windowListeners = new Map();

  const context = {
    console,
    setTimeout,
    clearTimeout,
    AbortController,
    FormData: class MockFormData {
      constructor() {
        this.entries = [];
      }

      append(key, value) {
        this.entries.push([key, value]);
      }
    },
    localStorage: {
      getItem() {
        return null;
      },
      setItem() {},
      removeItem() {},
    },
    document: {
      createElement() {
        let text = "";
        return {
          set textContent(value) {
            text = value ?? "";
          },
          get innerHTML() {
            return String(text)
              .replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;");
          },
        };
      },
      body: {
        classList: {
          add() {},
          remove() {},
        },
      },
    },
    window: {
      marked: null,
      hljs: null,
      addEventListener(type, handler) {
        windowListeners.set(type, handler);
      },
      removeEventListener(type) {
        windowListeners.delete(type);
      },
    },
    alert() {},
    confirm() {
      return true;
    },
    Vue: {
      createApp(options) {
        capturedOptions = options;
        return {
          mount() {},
        };
      },
    },
  };

  vm.runInNewContext(script, context, { filename: "script.js" });
  return { options: capturedOptions, context, windowListeners };
}

function createVm(overrides = {}) {
  const { options, context } = loadAppOptions();
  const state = {
    ...options.data(),
    $refs: {
      fileInput: { value: "" },
    },
    $nextTick(callback) {
      callback?.();
    },
    ...overrides,
  };

  for (const [name, fn] of Object.entries(options.methods || {})) {
    state[name] = fn.bind(state);
  }

  for (const [name, getter] of Object.entries(options.computed || {})) {
    Object.defineProperty(state, name, {
      enumerable: true,
      get() {
        return getter.call(state);
      },
    });
  }

  return { vm: state, context };
}

const checks = [
  {
    name: "uses the new centered floating shell instead of the old sidebar wrapper",
    run() {
      assert.match(index, /class="app-shell"/);
      assert.match(index, /class="top-nav"/);
      assert.match(index, /class="workspace"/);
      assert.match(index, /class="composer-dock"/);
      assert.doesNotMatch(index, /class="sidebar"/);
      assert.doesNotMatch(index, /class="app-wrapper"/);
    },
  },
  {
    name: "uses the equal-module Maintenance M branding",
    run() {
      assert.match(index, /logo-ragtenance\.svg/);
      assert.doesNotMatch(index, /logo-horse\.svg/);
      assert.match(css, /\.brand-mark/);
      assert.match(logo, /<path id="maintenance-module"/);
      assert.doesNotMatch(logo, /<rect id="maintenance-module"/);
      assert.equal((logo.match(/<use href="#maintenance-module"/g) || []).length, 2);
      assert.equal((logo.match(/<use href="#maintenance-module-top"/g) || []).length, 2);
      assert.equal((logo.match(/<use href="#maintenance-module-bottom"/g) || []).length, 2);
      assert.match(logo, /Q0 0 5 2\.5/);
      assert.match(logo, /Q34 37 29 34\.5/);
      assert.match(logo, /Q0 20 0 15/);
      assert.match(logo, /M0 0 L34 17 V37 L0 20 Z/);
      assert.match(logo, /L59 35 Q64 37\.5 69 35/);
      assert.match(logo, /L69 55 Q64 57\.5 59 55/);
      assert.doesNotMatch(logo, /horse|pony|马形/i);
      assert.doesNotMatch(index, /🐱/u);
    },
  },
  {
    name: "uses the evidence-blue palette without the old warm paper colors",
    run() {
      assert.match(css, /--blue-canvas:\s*#F3F8FD/i);
      assert.match(css, /--blue-surface:\s*#F8FBFE/i);
      assert.match(css, /--blue-ink:\s*#102A43/i);
      assert.match(css, /--blue-navy:\s*#123B66/i);
      assert.match(css, /--blue-main:\s*#2474C8/i);
      assert.match(css, /--blue-signal:\s*#55A7F3/i);
      assert.match(css, /--danger:\s*#B84242/i);
      assert.match(css, /repeating-linear-gradient\(95deg, rgba\(18, 59, 102, 0\.022\)/i);
      assert.match(css, /repeating-linear-gradient\(6deg, rgba\(18, 59, 102, 0\.014\)/i);
      assert.doesNotMatch(css, /#(?:F4ECD8|ECE0C4|FBF5E3|EDDFBC|C2402C|D95E3B|D9A441)/i);
      assert.doesNotMatch(css, /--primary-color:\s*#ff9e99/i);
      assert.doesNotMatch(css, /--bg-color:\s*#fff5f5/i);
    },
  },
  {
    name: "submits authentication through native form semantics without Enter key detection",
    run() {
      const authFormMarkup = index.match(/<form class="auth-form"[\s\S]*?<\/form>/)?.[0] || "";
      assert.match(authFormMarkup, /@submit\.prevent="handleAuthSubmit"/);
      assert.match(authFormMarkup, /<button type="submit" class="primary-action"/);
      assert.match(authFormMarkup, /<button type="button" class="text-action"/);
      assert.doesNotMatch(authFormMarkup, /@keydown(?:\.enter)?|keyCode|event\.key/);
      assert.doesNotMatch(authFormMarkup, /@click="handleAuthSubmit"/);
    },
  },
  {
    name: "keeps backend-facing API routes intact",
    run() {
      assert.match(backendApi, /include_router/);
      assert.match(backendRouterAuth, /\/auth\/register/);
      assert.match(backendRouterAuth, /\/auth\/login/);
      assert.match(backendRouterAuth, /\/auth\/me/);
      assert.match(backendRouterChat, /\/chat/);
      assert.match(backendRouterChat, /request\.context_files/);
      assert.match(backendRouterChat, /run_chat_stream/);
      assert.match(backendRouterSessions, /\/sessions/);
      assert.match(backendRouterSessions, /storage\./);
      assert.match(backendRouterDocuments, /\/documents\/upload/);
      assert.match(backendRouterDocuments, /DocumentService/);
      assert.match(backendRouterDocuments, /get_document_service/);
      [
        "/auth/me",
        "/auth/login",
        "/auth/register",
        "/chat/stream",
        "/sessions",
        "/documents",
        "/documents/upload",
      ].forEach((route) => assert.ok(script.includes(route), `missing ${route}`));
    },
  },
  {
    name: "buffers streaming output and avoids deep message watchers",
    run() {
      assert.match(script, /streamBuffer/);
      assert.match(script, /scheduleStreamFlush/);
      assert.match(script, /flushStreamBuffer/);
      assert.match(script, /streamFlushTimer/);
      assert.match(script, /streamFlushIntervalMs/);
      assert.match(script, /scheduleScrollToBottom/);
      assert.doesNotMatch(script, /deep:\s*true/);
      assert.doesNotMatch(index, /parseMarkdown\(msg\.text\)/);
    },
  },
  {
    name: "keeps structured RAG steps in a default-collapsed thinking process",
    run() {
      assert.match(index, /<details[^>]*class="thinking-process-details"/);
      assert.doesNotMatch(index, /<details[^>]*class="thinking-process-details"[^>]*\sopen(?:\s|>|=)/);
      assert.match(index, /思考过程/);
      assert.match(index, /step\.level/);
      assert.match(index, /step\.signal/);

      const { vm } = createVm({
        messages: [{ id: "bot", text: "answer", isUser: false, isThinking: false, ragSteps: [] }],
      });
      vm.scheduleScrollToBottom = () => {};
      const type = vm.consumeSseEvent(
        'data: {"type":"rag_step","step":{"icon":"✏️","label":"Level 1","detail":"rewrite","level":1,"signal":"anchor_mismatch"}}',
        0,
      );

      assert.equal(type, "rag_step");
      assert.equal(vm.messages[0].ragSteps[0].level, 1);
      assert.equal(vm.messages[0].ragSteps[0].signal, "anchor_mismatch");
    },
  },
  {
    name: "exposes history and knowledge as floating panels",
    run() {
      assert.match(index, /history-panel/);
      assert.match(index, /knowledge-view/);
      assert.match(script, /handleKnowledge/);
    },
  },
  {
    name: "supports global file picking from chat, page-level drop zone, and a top upload progress bar",
    run() {
      assert.match(index, /type="file"[^>]*multiple/);
      assert.match(index, /ref="globalFileInput"/);
      assert.match(index, /composer-upload-tray/);
      assert.match(index, /class="upload-actions"/);
      assert.match(index, /upload-trigger/);
      assert.match(index, /fa-cloud-arrow-up/);
      assert.match(index, /@click="triggerUploadPicker"/);
      assert.match(index, /:disabled="!selectedFiles.length \|\| isUploading"/);
      assert.match(index, /upload-status-bar/);
      assert.match(index, /page-drop-overlay/);
      assert.match(script, /maxUploadFiles/);
      assert.match(script, /queueSelectedFiles/);
      assert.match(script, /handleWindowDrop/);
      assert.match(script, /triggerUploadPicker/);
      assert.match(script, /pendingContextFiles/);
      assert.match(script, /context_files/);
      assert.match(css, /\.upload-actions\s*\{[\s\S]*display:\s*inline-grid;[\s\S]*grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/);
      assert.match(css, /\.upload-actions \.ghost-action\s*\{[\s\S]*width:\s*142px;/);
      assert.match(css, /\.upload-actions \.ghost-action:hover:not\(:disabled\)/);
      assert.match(css, /\.selected-files > \.primary-action\s*\{\s*display:\s*none;/);
    },
  },
  {
    name: "limits queued files to the configured maximum",
    run() {
      const { vm } = createVm();
      const files = Array.from({ length: 7 }, (_, idx) => ({
        name: `doc-${idx + 1}.pdf`,
        size: idx + 1,
        lastModified: idx + 100,
      }));

      vm.queueSelectedFiles(files);

      assert.equal(vm.selectedFiles.length, vm.maxUploadFiles);
      assert.equal(vm.selectedFiles[0].name, "doc-1.pdf");
      assert.equal(vm.selectedFiles.at(-1).name, `doc-${vm.maxUploadFiles}.pdf`);
    },
  },
  {
    name: "dropping files on the page queues them and starts upload in chat view",
    async run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "admin", role: "admin" },
        activeView: "chat",
      });

      let uploadTriggered = false;
      vm.uploadDocument = async () => {
        uploadTriggered = true;
      };

      await vm.handleWindowDrop({
        preventDefault() {},
        dataTransfer: {
          files: [{ name: "dragged.pdf", size: 1, lastModified: 1 }],
        },
      });

      assert.equal(vm.selectedFiles.length, 1);
      assert.equal(vm.selectedFiles[0].name, "dragged.pdf");
      assert.equal(uploadTriggered, true);
    },
  },
  {
    name: "clicking the chat upload trigger opens the shared file picker",
    run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "admin", role: "admin" },
      });
      let clicked = false;
      vm.$refs.globalFileInput = {
        click() {
          clicked = true;
        },
      };

      vm.triggerUploadPicker();

      assert.equal(clicked, true);
    },
  },
  {
    name: "uploaded files remain pending until the current chat turn consumes them as context",
    async run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "admin", role: "admin" },
        selectedFiles: [{ name: "manual.pdf", size: 1, lastModified: 1 }],
      });
      vm.uploadSingleFile = async () => ({ filename: "manual.pdf", message: "ok" });
      vm.loadDocuments = async () => {};

      await vm.uploadDocument();

      assert.deepEqual(Array.from(vm.pendingContextFiles.map((file) => file.filename)), ["manual.pdf"]);

      let streamedOptions = null;
      vm.userInput = "总结这份文档";
      vm.resetTextareaHeight = () => {};
      vm.scheduleScrollToBottom = () => {};
      vm.streamChatToBotSlot = async (_text, _idx, options) => {
        streamedOptions = options;
        return true;
      };

      await vm.handleSend();

      assert.deepEqual(Array.from(streamedOptions.contextFiles), ["manual.pdf"]);
      assert.equal(vm.pendingContextFiles.length, 0);
    },
  },
  {
    name: "sending while upload is active waits and uses that file in the current turn",
    async run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "admin", role: "admin" },
        isUploading: true,
      });
      let releaseUpload = null;
      vm.waitForActiveUpload = () =>
        new Promise((resolve) => {
          releaseUpload = () => {
            vm.addPendingContextFile({ filename: "slow.pdf" });
            vm.isUploading = false;
            resolve();
          };
        });
      let streamedOptions = null;
      vm.userInput = "分析这个文档";
      vm.resetTextareaHeight = () => {};
      vm.scheduleScrollToBottom = () => {};
      vm.streamChatToBotSlot = async (_text, _idx, options) => {
        streamedOptions = options;
        return true;
      };

      const sendPromise = vm.handleSend();
      assert.equal(streamedOptions, null);
      releaseUpload();
      await sendPromise;

      assert.deepEqual(Array.from(streamedOptions.contextFiles), ["slow.pdf"]);
      assert.equal(vm.pendingContextFiles.length, 0);
    },
  },
  {
    name: "failed chat streaming keeps attached context files available for retry",
    async run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "admin", role: "admin" },
        pendingContextFiles: [{ filename: "retry.pdf", addedAt: 1 }],
      });
      let streamedOptions = null;
      vm.userInput = "分析这个文档";
      vm.resetTextareaHeight = () => {};
      vm.scheduleScrollToBottom = () => {};
      vm.streamChatToBotSlot = async (_text, _idx, options) => {
        streamedOptions = options;
        return false;
      };

      await vm.handleSend();

      assert.deepEqual(Array.from(streamedOptions.contextFiles), ["retry.pdf"]);
      assert.deepEqual(Array.from(vm.pendingContextFiles.map((file) => file.filename)), ["retry.pdf"]);
    },
  },
  {
    name: "computes a real upload progress percentage across the queued files",
    run() {
      const { vm } = createVm({
        selectedFiles: [
          { name: "a.pdf", size: 10, lastModified: 1 },
          { name: "b.pdf", size: 20, lastModified: 2 },
        ],
        completedUploads: 1,
        currentUploadPercent: 50,
      });

      assert.equal(vm.uploadProgressPercent, 75);
    },
  },
  {
    name: "threads attached context files through the main backend RAG filter",
    run() {
      assert.match(backendSchemas, /context_files:\s*Optional\[List\[str\]\]/);
      assert.match(backendRouterChat, /request\.context_files/);
      assert.match(backendAgent, /context_files/);
      assert.match(backendTools, /set_rag_context_files/);
      assert.match(backendTools, /run_rag_graph\(query,\s*context_files=/);
      assert.match(backendRagPipeline, /context_files/);
      assert.match(backendRagRetrieval, /filename in \[/);
      assert.match(backendRagUtils, /retrieve_candidate_pool/);
      assert.match(backendRagPipeline, /strict_scope_filter/);
      assert.doesNotMatch(backendRagPipeline, /retrieve_context_documents\(/);
      assert.match(backendRagExecution, /_with_retrieved_context_instruction/);
      assert.match(backendRagExecution, /model_instance\.astream/);
      assert.match(backendRagPipeline, /JSON/i);
      assert.match(backendRagPipeline, /fallback_router_node/);
    },
  },
  {
    name: "sends and persists the per-message comprehensive override",
    async run() {
      const { vm } = createVm({
        token: "token",
        currentUser: { username: "user", role: "user" },
        forceComprehensive: true,
        userInput: "比较两个方案",
      });
      let streamedOptions = null;
      vm.resetTextareaHeight = () => {};
      vm.scheduleScrollToBottom = () => {};
      vm.streamChatToBotSlot = async (_text, _idx, options) => {
        streamedOptions = options;
        return true;
      };

      await vm.handleSend();

      assert.equal(vm.messages[0].forceComprehensive, true);
      assert.equal(streamedOptions.forceComprehensive, true);
      assert.match(index, /为我启用综合查询/);
      assert.match(index, /intent_mode_degradation_error/);
    },
  },
  {
    name: "serializes only the boolean request override in chat payloads",
    async run() {
      const { vm } = createVm();
      let payload = null;
      vm.authFetch = async (_url, options) => {
        payload = JSON.parse(options.body);
        return {
          ok: true,
          body: {
            getReader() {
              return { read: async () => ({ done: true }) };
            },
          },
        };
      };
      vm.scheduleScrollToBottom = () => {};
      vm.messages = [vm.createBotMessage()];

      await vm.streamChatToBotSlot("比较", 0, { forceComprehensive: true });

      assert.equal(payload.force_comprehensive, true);
      assert.equal("intent_mode" in payload, false);
    },
  },
  {
    name: "regenerate reuses the original user message mode instead of composer state",
    async run() {
      const { vm } = createVm({ forceComprehensive: false });
      const user = vm.createUserMessage("比较", ["manual.pdf"], true);
      const bot = vm.createBotMessage("旧回答");
      vm.messages = [user, bot];
      vm.scheduleScrollToBottom = () => {};
      let options = null;
      vm.streamChatToBotSlot = async (_text, _idx, incoming) => {
        options = incoming;
        return true;
      };

      await vm.regenerateAssistantAt(1);

      assert.equal(options.forceComprehensive, true);
      assert.deepEqual(Array.from(options.contextFiles), ["manual.pdf"]);
    },
  },
];

const failures = [];

for (const check of checks) {
  try {
    await check.run();
    console.log(`PASS ${check.name}`);
  } catch (error) {
    failures.push({ check, error });
    console.error(`FAIL ${check.name}`);
    console.error(error.message);
  }
}

if (failures.length) {
  process.exitCode = 1;
}
