import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApuService } from '../../services/apu';

interface ChatMessage {
  text: string;
  isUser: boolean;
  timestamp: Date;
}

@Component({
  selector: 'app-chat-apus',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-apus.html',
  styleUrl: './chat-apus.scss',
})
export class ChatApus {
  messages: ChatMessage[] = [];
  userInput = '';
  isLoading = false;

  private static readonly STORAGE_KEY = 'mapus_chat_history';

  constructor(private apuService: ApuService) {
    this.loadHistory();
  }

  private loadHistory(): void {
    try {
      const saved = sessionStorage.getItem(ChatApus.STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        this.messages = parsed.map((m: any) => ({ ...m, timestamp: new Date(m.timestamp) }));
      }
    } catch {
      // ignore
    }
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
      const toSave = this.messages.slice(-50);
      sessionStorage.setItem(ChatApus.STORAGE_KEY, JSON.stringify(toSave));
    } catch {
      // ignore
    }
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

    this.apuService.chatAssistant(text).subscribe({
      next: (res: any) => {
        this.messages.push({ text: res.reply, isUser: false, timestamp: new Date() });
        this.isLoading = false;
        this.saveHistory();
      },
      error: () => {
        this.messages.push({
          text: 'Ocurrió un error al procesar tu mensaje. Intenta de nuevo.',
          isUser: false,
          timestamp: new Date(),
        });
        this.isLoading = false;
      },
    });
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
}
