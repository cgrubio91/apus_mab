import { Component, ChangeDetectorRef, ViewChild, ElementRef, AfterViewChecked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ApuService } from '../../services/apu';
import { sanitizeChatHtml } from '../../services/html-sanitizer';

interface ChatStage {
  phase: string;
  duration_ms: number;
}

interface ChatMessage {
  text: string;
  html?: SafeHtml;
  htmlRaw?: string;
  isUser: boolean;
  timestamp: Date;
  sqlQuery?: string;
  showSql?: boolean;
  stages?: ChatStage[];
  chartData?: ChartData | null;
  suggestedFollowups?: string[];
}

interface ChartData {
  labels: string[];
  values: number[];
  label: string;
}

@Component({
  selector: 'app-chat-apus',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-apus.html',
  styleUrl: './chat-apus.scss',
})
export class ChatApus implements AfterViewChecked {
  @ViewChild('scrollContainer') private scrollContainer!: ElementRef;

  messages: ChatMessage[] = [];
  userInput = '';
  isLoading = false;
  currentStages: ChatStage[] = [];
  currentSqlQuery = '';

  private static readonly STORAGE_KEY = 'mapus_chat_history';

  constructor(
    private apuService: ApuService,
    private cdr: ChangeDetectorRef,
    private sanitizer: DomSanitizer,
  ) {
    this.loadHistory();
  }

  ngAfterViewChecked(): void {
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    try {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    } catch { }
  }

  private loadHistory(): void {
    try {
      const saved = sessionStorage.getItem(ChatApus.STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        this.messages = parsed.map((m: any) => {
          const htmlRaw = m.htmlRaw ? sanitizeChatHtml(m.htmlRaw) : undefined;
          return {
            ...m,
            timestamp: new Date(m.timestamp),
            htmlRaw,
            html: htmlRaw ? this.sanitizer.bypassSecurityTrustHtml(htmlRaw) : undefined,
          };
        });
      }
    } catch { }
    if (this.messages.length === 0) {
      this.messages.push({
        text: 'Hola! Soy tu asistente de APUs. Pregúntame sobre proyectos, precios, insumos o lo que necesites.',
        isUser: false,
        timestamp: new Date(),
      });
    }
  }

  private saveHistory(): void {
    try {
      const toSave = this.messages.slice(-50).map(m => ({
        text: m.text,
        htmlRaw: m.htmlRaw,
        isUser: m.isUser,
        timestamp: m.timestamp,
        sqlQuery: m.sqlQuery,
        showSql: m.showSql,
        stages: m.stages,
        chartData: m.chartData,
        suggestedFollowups: m.suggestedFollowups,
      }));
      sessionStorage.setItem(ChatApus.STORAGE_KEY, JSON.stringify(toSave));
    } catch { }
  }

  private processText(text: string): { text: string; html?: SafeHtml; htmlRaw?: string } {
    if (text.includes('<table') || text.includes('<tr') || text.includes('<td')) {
      const clean = sanitizeChatHtml(text);
      return { text, html: this.sanitizer.bypassSecurityTrustHtml(clean), htmlRaw: clean };
    }
    return { text };
  }

  private detectChartData(text: string, results: any[]): ChartData | null {
    if (!results || results.length < 2) return null;
    const keys = Object.keys(results[0] || {});
    if (keys.length < 2) return null;

    const labelKey = keys.find(k => typeof results[0][k] === 'string' || typeof results[0][k] === 'number');
    const valueKey = keys.find(k =>
      k !== labelKey && typeof results[0][k] === 'number' && !k.includes('id') && !k.includes('ID')
    );
    if (!labelKey || !valueKey) return null;

    const labels = results.map(r => String(r[labelKey] ?? '').slice(0, 30));
    const values = results.map(r => Number(r[valueKey] ?? 0));
    if (values.some(v => isNaN(v))) return null;

    return { labels, values, label: valueKey.replace(/_/g, ' ') };
  }

  selectSuggestion(suggestion: string): void {
    this.userInput = suggestion;
    this.sendMessage();
  }

  sendMessage(): void {
    const text = this.userInput.trim();
    if (!text || this.isLoading) return;

    this.messages.push({ text, isUser: true, timestamp: new Date() });
    this.userInput = '';
    this.isLoading = true;
    this.currentStages = [];
    this.currentSqlQuery = '';
    this.cdr.markForCheck();

    this.apuService.chatAssistant(text).subscribe({
      next: (res: any) => {
        const processed = this.processText(res.reply);
        const chartData = this.detectChartData(res.reply, res.results || []);
        const msg: ChatMessage = {
          text: processed.text,
          html: processed.html,
          htmlRaw: processed.htmlRaw,
          isUser: false,
          timestamp: new Date(),
          sqlQuery: res.sql_query || undefined,
          showSql: false,
          stages: res.stages || [],
          chartData,
          suggestedFollowups: res.suggested_followups || [],
        };
        this.messages.push(msg);
        this.isLoading = false;
        this.currentStages = [];
        this.currentSqlQuery = '';
        this.saveHistory();
        this.cdr.markForCheck();
      },
      error: () => {
        this.messages.push({
          text: 'Ocurrió un error al procesar tu mensaje. Intenta de nuevo.',
          isUser: false,
          timestamp: new Date(),
        });
        this.isLoading = false;
        this.currentStages = [];
        this.cdr.markForCheck();
      },
    });
  }

  toggleSql(msg: ChatMessage): void {
    msg.showSql = !msg.showSql;
    this.saveHistory();
  }

  clearChat(): void {
    this.messages = [
      {
        text: 'Hola! Soy tu asistente de APUs. Pregúntame sobre proyectos, precios, insumos o lo que necesites.',
        isUser: false,
        timestamp: new Date(),
      },
    ];
    sessionStorage.removeItem(ChatApus.STORAGE_KEY);
  }

  totalTime(stages?: ChatStage[]): string {
    if (!stages?.length) return '';
    const total = stages.reduce((s, st) => s + st.duration_ms, 0);
    return (total / 1000).toFixed(1);
  }

  stageIcon(phase: string): string {
    if (phase.includes('SQL')) return '💡';
    if (phase.includes('Valid')) return '✅';
    if (phase.includes('Consult') || phase.includes('base')) return '📊';
    if (phase.includes('Redact')) return '✍️';
    return '⚙️';
  }

  maxChartValue(values: number[]): number {
    return Math.max(...values, 1);
  }

  trackById(index: number): number {
    return index;
  }
}
