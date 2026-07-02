
// @ts-ignore
import { marked } from 'https://cdnjs.cloudflare.com/ajax/libs/marked/15.0.0/lib/marked.esm.js'

interface Message {
  role: string
  content: string
  timestamp: string
  chatId: string
}

interface Chat {
  id: string
  title: string
  messages: Message[]
  lastTimestamp: string
  createdAt: string
}

interface ChatAppInterface {
  deleteChat: (chatId: string) => void;
  toggleModelMenu: () => void;
  selectModel: (model: string) => void;
  setTheme: (theme: 'light' | 'dark') => void;
  stopIngest: () => void;
}

declare global {
  interface Window {
    chatApp: ChatAppInterface;
    toggleModelMenu: () => void;
    selectModel: (model: string) => void;
    setTheme: (theme: 'light' | 'dark') => void;
  }
}

class ChatApp implements ChatAppInterface {
  private convElement: HTMLElement
  private promptInput: HTMLInputElement
  private spinner: HTMLElement
  private chatHistory: HTMLElement
  private chats: Map<string, Chat> = new Map()
  private currentChatId: string | null = null
  private currentModel: string = 'openai'

  // Ingest simulator state
  private ingestAbort: AbortController | null = null
  private ingestStats = { sent: 0, triggered: 0, invalid: 0, errors: 0 }

  constructor() {
    const convEl = document.getElementById('conversation')
    const promptEl = document.getElementById('prompt-input')
    const spinnerEl = document.getElementById('spinner')
    const historyEl = document.getElementById('chat-history')

    if (!convEl || !promptEl || !spinnerEl || !historyEl) {
      throw new Error('Required DOM elements not found')
    }

    this.convElement = convEl
    this.promptInput = promptEl as HTMLInputElement
    this.spinner = spinnerEl
    this.chatHistory = historyEl

    this.initEventListeners()
    this.initModelSelector()
    this.initThemeToggle()
    this.initIngest()
    this.loadChats().then(() => {
      // После загрузки чатов проверяем, нужно ли показать Grafana
      const showGrafana = localStorage.getItem('showGrafana') === 'true'
      if (showGrafana) {
        this.showGrafanaOnLoad()
      }
    })
    this.initMetricsButton()
  }

  private initEventListeners() {
    const form = document.querySelector('form')
    const newChatBtn = document.getElementById('new-chat')
    
    if (form) {
      form.addEventListener('submit', (e) => this.onSubmit(e).catch(this.onError))
    }
    
    if (newChatBtn) {
      newChatBtn.addEventListener('click', () => this.createNewChat())
    }
    
    // Close menus when clicking outside
    document.addEventListener('click', (e) => {
      const target = e.target as Element
      if (!target.closest('.chat-menu') && !target.closest('.chat-menu-button')) {
        document.querySelectorAll('.chat-menu.show').forEach(menu => {
          menu.classList.remove('show')
        })
      }
      if (!target.closest('.model-menu') && !target.closest('.model-selector')) {
        document.querySelectorAll('.model-menu.show').forEach(menu => {
          menu.classList.remove('show')
        })
      }
    })
  }

  private initModelSelector() {
    window.toggleModelMenu = this.toggleModelMenu.bind(this)
    window.selectModel = this.selectModel.bind(this)
  }

  private initThemeToggle() {
    window.setTheme = this.setTheme.bind(this)
    
    // Set initial theme
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' || 'light'
    this.setTheme(savedTheme)
  }

  private initMetricsButton() {
    const metricsItems = document.querySelectorAll('.metrics-menu-item')
    const inputForm = document.querySelector('.input-container form') as HTMLElement
    const contentContainer = document.querySelector('.content-container') as HTMLElement
    const grafanaContainer = document.querySelector('.grafana-container') as HTMLElement

    metricsItems.forEach(item => {
      item.addEventListener('click', (e) => {
        const target = (e.currentTarget as HTMLElement)
        if (target.textContent?.includes('Show/Hide Metrics')) {
          const isGrafanaVisible = grafanaContainer.classList.contains('show')
          if (isGrafanaVisible) {
            inputForm.classList.remove('hide-inputs')
            contentContainer.classList.remove('hide')
            grafanaContainer.classList.remove('show')
            localStorage.setItem('showGrafana', 'false')
          } else {
            inputForm.classList.add('hide-inputs')
            contentContainer.classList.add('hide')
            grafanaContainer.classList.add('show')
            localStorage.setItem('showGrafana', 'true')
          }
        }
      })
    })
  }

  private generateChatId(): string {
    return `chat-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
  }

  private async loadChats() {
    const response = await fetch('/chat/')
    const messages = await response.json() as Message[]
    
    // Group messages by chatId
    messages.forEach(msg => {
      if (!msg.chatId) {
        console.warn('Message without chatId:', msg)
        return // Skip messages without chatId
      }

      let chat = this.chats.get(msg.chatId)
      if (!chat) {
        // Create new chat if it doesn't exist
        chat = {
          id: msg.chatId,
          title: '',
          messages: [],
          lastTimestamp: msg.timestamp,
          createdAt: msg.timestamp
        }
        this.chats.set(msg.chatId, chat)
      }

      // Add message to chat
      chat.messages.push(msg)
      
      // Update timestamps
      const msgTime = new Date(msg.timestamp).getTime()
      const lastTime = new Date(chat.lastTimestamp).getTime()
      if (msgTime > lastTime) {
        chat.lastTimestamp = msg.timestamp
      }
      
      // Update title if this is the first user message
      if (!chat.title && msg.role === 'user') {
        chat.title = this.generateChatTitle(msg)
      }
    })

    // Sort messages within each chat by timestamp
    for (const chat of this.chats.values()) {
      chat.messages.sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      )
    }

    this.renderChatHistory()
    if (this.chats.size > 0) {
      // Switch to the most recent chat
      const latestChat = Array.from(this.chats.values())
        .sort((a, b) => new Date(b.lastTimestamp).getTime() - new Date(a.lastTimestamp).getTime())[0]
      this.switchChat(latestChat.id)
    }
  }

  private generateChatTitle(firstMsg: Message): string {
    // Remove markdown symbols and limit to first sentence or N characters
    const cleanContent = firstMsg.content
      .replace(/[#*`]/g, '') // Remove markdown symbols
      .trim()
    
    // Try to get first sentence (end with . ! or ?)
    const sentenceMatch = cleanContent.match(/^[^.!?]+[.!?]/)
    if (sentenceMatch) {
      const sentence = sentenceMatch[0].trim()
      return sentence.length > 50 ? sentence.slice(0, 47) + '...' : sentence
    }
    
    // If no sentence found, just take first N characters
    return cleanContent.length > 50 ? cleanContent.slice(0, 47) + '...' : cleanContent
  }

  private formatTime(dateStr: string): string {
    const date = new Date(dateStr)
    return date.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit',
      hour12: false 
    })
  }

  private renderChatHistory() {
    if (!this.chatHistory) return
    
    this.chatHistory.innerHTML = ''

    // Group chats by date using createdAt
    const chatsByDate = new Map<string, Chat[]>()
    
    Array.from(this.chats.values())
      .sort((a, b) => b.lastTimestamp.localeCompare(a.lastTimestamp))
      .forEach(chat => {
        const date = new Date(chat.createdAt).toLocaleDateString()
        if (!chatsByDate.has(date)) {
          chatsByDate.set(date, [])
        }
        chatsByDate.get(date)?.push(chat)
      })

    // Sort dates in reverse chronological order
    const sortedDates = Array.from(chatsByDate.keys())
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())

    // Render groups
    sortedDates.forEach(date => {
      const chats = chatsByDate.get(date)
      if (!chats || chats.length === 0) return

      const group = document.createElement('div')
      group.className = 'chat-history-group'

      const dateHeader = document.createElement('div')
      dateHeader.className = 'chat-history-date'
      
      // Split date into weekday and date parts
      const [weekday, dateStr] = this.formatDate(date).split(' ')
      dateHeader.innerHTML = `${weekday} <span>${dateStr}</span>`
      
      group.appendChild(dateHeader)

      // Sort chats within the group by last message time
      chats.sort((a, b) => new Date(b.lastTimestamp).getTime() - new Date(a.lastTimestamp).getTime())
        .forEach(chat => {
          const div = document.createElement('div')
          div.className = `chat-history-item ${chat.id === this.currentChatId ? 'active' : ''}`
          
          const contentWrapper = document.createElement('div')
          contentWrapper.className = 'chat-content'
          contentWrapper.onclick = () => this.switchChat(chat.id)
          
          const titleRow = document.createElement('div')
          titleRow.className = 'title-row'
          
          const title = document.createElement('div')
          title.className = 'title'
          title.textContent = chat.title || 'New Chat'
          
          const time = document.createElement('div')
          time.className = 'chat-time'
          time.textContent = this.formatTime(chat.lastTimestamp)
          
          titleRow.appendChild(title)
          titleRow.appendChild(time)
          contentWrapper.appendChild(titleRow)
          div.appendChild(contentWrapper)

          const menuButton = document.createElement('button')
          menuButton.className = 'chat-menu-button'
          menuButton.innerHTML = '<i class="bi bi-three-dots-vertical"></i>'
          menuButton.onclick = (e) => {
            e.stopPropagation()
            this.toggleChatMenu(chat.id)
          }
          div.appendChild(menuButton)

          const menu = document.createElement('div')
          menu.className = 'chat-menu'
          menu.setAttribute('data-chat-id', chat.id)
          menu.innerHTML = `
            <div class="chat-menu-item delete" onclick="event.stopPropagation(); window.chatApp.deleteChat('${chat.id}');">
              <i class="bi bi-trash"></i>
              Delete chat
            </div>
          `
          div.appendChild(menu)
          group.appendChild(div)
        })

      if (group.children.length > 1) { // Only add group if it has chats (>1 because of dateHeader)
        this.chatHistory.appendChild(group)
      }
    })
  }

  private formatDate(dateStr: string): string {
    const date = new Date(dateStr)
    
    // Get weekday name
    const weekday = date.toLocaleDateString('en-US', { weekday: 'long' })
    
    // Format date as DD.MM.YYYY
    const day = date.getDate().toString().padStart(2, '0')
    const month = (date.getMonth() + 1).toString().padStart(2, '0')
    const year = date.getFullYear()
    
    return `${weekday} ${day}.${month}.${year}`
  }

  private toggleChatMenu(chatId: string) {
    // Close all other menus first
    document.querySelectorAll('.chat-menu.show').forEach(menu => {
      if (menu.getAttribute('data-chat-id') !== chatId) {
        menu.classList.remove('show')
      }
    })

    // Toggle current menu
    const menu = document.querySelector(`.chat-menu[data-chat-id="${chatId}"]`)
    if (menu) {
      menu.classList.toggle('show')
    }
  }

  private switchChat(chatId: string) {
    this.currentChatId = chatId
    this.convElement.innerHTML = ''
    const chat = this.chats.get(chatId)
    if (chat) {
      chat.messages.forEach(msg => this.renderMessage(msg))
      this.renderChatHistory()
      
      // Scroll to the beginning of the chat when switching
      const contentContainer = document.querySelector('.content-container')
      if (contentContainer) {
        contentContainer.scrollTop = 0
      }
    }
  }

  private cleanupEmptyChats() {
    for (const [chatId, chat] of this.chats.entries()) {
      if (chat.messages.length === 0 && chat.title === 'New Chat' && chatId !== this.currentChatId) {
        this.chats.delete(chatId)
      }
    }
    this.renderChatHistory()
  }

  private createNewChat() {
    // Cleanup any empty chats before creating a new one
    this.cleanupEmptyChats()

    const chatId = this.generateChatId()
    const timestamp = new Date().toISOString()
    
    this.chats.set(chatId, {
      id: chatId,
      title: 'New Chat',
      messages: [],
      lastTimestamp: timestamp,
      createdAt: timestamp
    })
    
    this.switchChat(chatId)
  }

  private renderMessage(message: Message) {
    const { timestamp, role, content } = message
    const id = `msg-${timestamp}`
    let msgDiv = document.getElementById(id)
    if (!msgDiv) {
      msgDiv = document.createElement('div')
      msgDiv.id = id
      msgDiv.title = `${role} at ${timestamp}`
      msgDiv.classList.add(role)
      this.convElement.appendChild(msgDiv)
    }
    msgDiv.innerHTML = marked.parse(content)
    
    // Scroll to the last message
    const contentContainer = document.querySelector('.content-container')
    if (contentContainer) {
      contentContainer.scrollTop = contentContainer.scrollHeight
    }
  }

  private async onSubmit(e: SubmitEvent) {
    e.preventDefault()
    
    if (!this.currentChatId) {
      this.createNewChat()
    }

    this.spinner.classList.add('active')
    const formData = new FormData(e.target as HTMLFormElement)
    const prompt = formData.get('prompt') as string
    
    // Create message object
    const messageData = {
      content: prompt,
      chatId: this.currentChatId
    }
    
    formData.set('prompt', JSON.stringify(messageData))
    formData.append('model', this.currentModel)
    
    console.log('Submitting with chatId:', this.currentChatId)
    this.promptInput.value = ''
    this.promptInput.disabled = true

    try {
      const response = await fetch('/chat/', { method: 'POST', body: formData })
      await this.onFetchResponse(response)
    } catch (error) {
      this.onError(error)
    }
  }

  private async onFetchResponse(response: Response) {
    if (!response.ok || !response.body) {
      throw new Error(`Unexpected response: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let text = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        
        text += decoder.decode(value)
        const messages = text.split('\n')
          .filter(line => line.length > 1)
          .map(j => JSON.parse(j)) as Message[]
        
        messages.forEach(msg => {
          // Temporary fix: use current chatId if message doesn't have one
          if (!msg.chatId && this.currentChatId) {
            msg.chatId = this.currentChatId
            console.log('Added chatId to new message:', msg)
          }

          this.renderMessage(msg)
          if (msg.chatId) {
            const chat = this.chats.get(msg.chatId)
            if (chat) {
              chat.messages.push(msg)
              if (msg.timestamp > chat.lastTimestamp) {
                chat.lastTimestamp = msg.timestamp
              }
              // Update title only for the first message in chat
              if (chat.title === 'New Chat' && msg.role === 'user') {
                chat.title = this.generateChatTitle(msg)
                console.log('Updated chat title for new message:', chat.title)
                this.renderChatHistory()
              }
            }
          }
        })
      }
    } catch (error) {
      console.error('Error processing response:', error)
    } finally {
      this.spinner.classList.remove('active')
      this.promptInput.disabled = false
      this.promptInput.focus()
    }
  }

  private onError(error: any) {
    console.error(error)
    document.getElementById('error')?.classList.remove('d-none')
    this.spinner.classList.remove('active')
  }

  public async deleteChat(chatId: string): Promise<void> {
    try {
      // Delete chat from server
      const response = await fetch('/chat/delete', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ chatId })
      })

      const result = await response.json()
      
      if (result.success) {
        console.log(`Deleted ${result.deleted_messages_count} messages from chat ${result.chat_id}`)
        
        // Delete chat locally
        this.chats.delete(chatId)
        if (this.currentChatId === chatId) {
          if (this.chats.size > 0) {
            const latestChat = Array.from(this.chats.values())
              .sort((a, b) => new Date(b.lastTimestamp).getTime() - new Date(a.lastTimestamp).getTime())[0]
            this.switchChat(latestChat.id)
          } else {
            this.currentChatId = null
            this.convElement.innerHTML = ''
          }
        }
        this.renderChatHistory()
      } else {
        console.error('Failed to delete chat:', result)
      }
    } catch (error) {
      console.error('Error deleting chat:', error)
    }
  }

  public toggleModelMenu(): void {
    const menu = document.querySelector('.model-menu') as HTMLElement
    menu.classList.toggle('show')
  }

  public selectModel(model: string): void {
    this.currentModel = model;
    const currentModelSpan = document.querySelector('.current-model') as HTMLElement;
    currentModelSpan.textContent = model.charAt(0).toUpperCase() + model.slice(1);
    this.toggleModelMenu();

    // Notify backend of model change
    fetch('/set_model/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model })
    }).catch(e => {
      console.error('Failed to notify backend of model change', e);
    });
  }

  public setTheme(theme: 'light' | 'dark'): void {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }

  private showGrafanaOnLoad() {
    const grafanaContainer = document.querySelector('.grafana-container') as HTMLElement
    const contentContainer = document.querySelector('.content-container') as HTMLElement
    const inputForm = document.querySelector('.input-container form') as HTMLElement

    grafanaContainer.classList.add('show')
    contentContainer.classList.add('hide')
    inputForm.classList.add('hide-inputs')

    // Update the text in the metrics selector
    const currentMetrics = document.querySelector('.current-metrics')
    if (currentMetrics) {
      currentMetrics.textContent = 'Grafana'
    }
  }

  // -------------------------------------------------------------------------
  // Log Ingest Simulator
  // -------------------------------------------------------------------------

  private initIngest() {
    this.loadIngestSources()

    const modeSelect = document.getElementById('ingest-mode') as HTMLSelectElement
    const delayGroup = document.getElementById('ingest-delay-group') as HTMLElement
    modeSelect.addEventListener('change', () => {
      delayGroup.style.display = modeSelect.value === 'delay' ? '' : 'none'
    })

    const startBtn = document.getElementById('ingest-start') as HTMLButtonElement
    const stopBtn = document.getElementById('ingest-stop') as HTMLButtonElement
    startBtn.addEventListener('click', () => this.startIngest())
    stopBtn.addEventListener('click', () => this.stopIngest())
  }

  private async loadIngestSources() {
    const select = document.getElementById('ingest-source') as HTMLSelectElement
    if (!select) return
    try {
      const resp = await fetch('/logs/sources')
      const data = await resp.json() as { sources: { name: string; lines: number; size: number }[] }
      select.innerHTML = ''
      if (!data.sources || data.sources.length === 0) {
        const opt = document.createElement('option')
        opt.textContent = 'No sample files found'
        opt.value = ''
        select.appendChild(opt)
        return
      }
      for (const s of data.sources) {
        const opt = document.createElement('option')
        opt.value = s.name
        opt.textContent = `${s.name}  (${s.lines.toLocaleString()} lines)`
        select.appendChild(opt)
      }
    } catch (e) {
      console.error('Failed to load ingest sources', e)
    }
  }

  private resetIngestStats() {
    this.ingestStats = { sent: 0, triggered: 0, invalid: 0, errors: 0 }
    this.renderIngestStats()
    const bar = document.getElementById('ingest-progress-bar')
    if (bar) bar.style.width = '0%'
    const log = document.getElementById('ingest-log')
    if (log) log.innerHTML = ''
  }

  private renderIngestStats() {
    const setVal = (id: string, v: number) => {
      const el = document.getElementById(id)
      if (el) el.textContent = String(v)
    }
    setVal('ingest-stat-sent', this.ingestStats.sent)
    setVal('ingest-stat-triggered', this.ingestStats.triggered)
    setVal('ingest-stat-invalid', this.ingestStats.invalid)
    setVal('ingest-stat-errors', this.ingestStats.errors)
  }

  private appendIngestLine(text: string, kind: 'info' | 'ok' | 'warn' | 'err' = 'info') {
    const log = document.getElementById('ingest-log')
    if (!log) return
    const div = document.createElement('div')
    div.className = `ingest-log-line ingest-log-${kind}`
    div.textContent = text
    log.appendChild(div)
    // keep only the last 400 lines to avoid runaway DOM size
    while (log.children.length > 400) {
      log.removeChild(log.firstChild as Node)
    }
    log.scrollTop = log.scrollHeight
  }

  public async startIngest() {
    const source = (document.getElementById('ingest-source') as HTMLSelectElement).value
    if (!source) {
      this.appendIngestLine('No source file selected.', 'err')
      return
    }
    const limit = parseInt((document.getElementById('ingest-limit') as HTMLInputElement).value, 10) || 50
    const mode = (document.getElementById('ingest-mode') as HTMLSelectElement).value
    const delay = parseFloat((document.getElementById('ingest-delay') as HTMLInputElement).value) || 0

    const body: Record<string, unknown> = { source, limit }
    if (mode === 'delay') body.delay = delay
    if (mode === 'realtime') body.realtime = true

    this.resetIngestStats()
    this.appendIngestLine(`▶ Streaming ${limit} lines from ${source} (${mode})…`, 'info')

    const startBtn = document.getElementById('ingest-start') as HTMLButtonElement
    const stopBtn = document.getElementById('ingest-stop') as HTMLButtonElement
    startBtn.disabled = true
    stopBtn.disabled = false

    this.ingestAbort = new AbortController()

    try {
      const resp = await fetch('/logs/simulate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: this.ingestAbort.signal,
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`)
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const evt = JSON.parse(line)
            this.handleIngestEvent(evt, limit)
          } catch {
            // ignore parse errors on partial chunks
          }
        }
      }
      this.appendIngestLine('✔ Done.', 'ok')
    } catch (e: unknown) {
      const err = e as Error
      if (err.name === 'AbortError') {
        this.appendIngestLine('■ Stopped by user.', 'warn')
      } else {
        this.appendIngestLine(`✖ Error: ${err.message}`, 'err')
      }
    } finally {
      this.ingestAbort = null
      startBtn.disabled = false
      stopBtn.disabled = true
    }
  }

  private handleIngestEvent(evt: Record<string, unknown>, limit: number) {
    if (evt.error) {
      this.ingestStats.errors++
      this.appendIngestLine(`✖ ${evt.error}`, 'err')
      this.renderIngestStats()
      return
    }

    this.ingestStats.sent++
    if (evt.valid === false) {
      this.ingestStats.invalid++
    }
    if (evt.triggered === true) {
      this.ingestStats.triggered++
    }

    const sent = evt.sent as number
    const pct = Math.min(100, Math.round((sent / limit) * 100))
    const bar = document.getElementById('ingest-progress-bar')
    if (bar) bar.style.width = `${pct}%`

    // Only print interesting lines (errors/warns/invalids) to keep noise down
    const raw = (evt.raw as string) || ''
    const level = evt.level as string | undefined
    if (evt.triggered) {
      this.appendIngestLine(`[${level}] ${raw}`, 'warn')
    } else if (evt.valid === false) {
      this.appendIngestLine(`[INVALID] ${raw}`, 'err')
    }
    this.renderIngestStats()
  }

  public stopIngest() {
    if (this.ingestAbort) {
      this.ingestAbort.abort()
    }
  }
}

// Initialize the app
const chatApp = new ChatApp()
window.chatApp = chatApp