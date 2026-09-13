import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatTableModule } from '@angular/material/table';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatButtonModule } from '@angular/material/button';
import { MatInputModule } from '@angular/material/input';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatSelectModule } from '@angular/material/select';
import { MatCardModule } from '@angular/material/card';

interface Fonte {
  id: string;
  uf: string;
  nome: string;
  url: string;
  selecionada?: boolean;
}

@Component({
  selector: 'app-fontes',
  imports: [
    CommonModule,
    FormsModule,
    MatTableModule,
    MatCheckboxModule,
    MatButtonModule,
    MatInputModule,
    MatFormFieldModule,
    MatIconModule,
    MatSelectModule,
    MatCardModule
  ],
  templateUrl: './fontes.html',
  styleUrl: './fontes.scss',
})
export class Fontes implements OnInit {
  private http = inject(HttpClient);
  
  fontes: Fonte[] = [];
  filteredFontes: Fonte[] = [];
  ufs: string[] = [];
  
  busca: string = '';
  
  novaFonte: Partial<Fonte> = { uf: '', nome: '', url: '', id: '' };

  displayedColumns: string[] = ['selecionada', 'id', 'uf', 'nome', 'url', 'acoes'];

  ngOnInit() {
    this.carregar();
  }

  carregar() {
    this.http.get<{ itens: Fonte[], ufs: string[] }>('/api/fontes').subscribe(res => {
      this.fontes = res.itens || [];
      this.ufs = res.ufs || [];
      this.filtrar();
    });
  }

  filtrar() {
    if (!this.busca) {
      this.filteredFontes = [...this.fontes];
    } else {
      const b = this.busca.toLowerCase();
      this.filteredFontes = this.fontes.filter(f => 
        (f.nome || '').toLowerCase().includes(b) ||
        (f.id || '').toLowerCase().includes(b) ||
        (f.uf || '').toLowerCase().includes(b) ||
        (f.url || '').toLowerCase().includes(b)
      );
    }
  }

  toggle(fonte: Fonte) {
    this.http.post('/api/fontes/selecionar', { id: fonte.id, selecionada: !fonte.selecionada }).subscribe(() => {
      fonte.selecionada = !fonte.selecionada;
    });
  }

  incluir() {
    if (!this.novaFonte.id || !this.novaFonte.nome || !this.novaFonte.url) {
      alert('Preencha id, nome e url da nova fonte');
      return;
    }
    this.http.post<{ item: Fonte }>('/api/fontes/incluir', this.novaFonte).subscribe(res => {
      this.fontes.push(res.item);
      this.novaFonte = { uf: '', nome: '', url: '', id: '' };
      this.filtrar();
    });
  }

  excluir(id: string) {
    if (confirm('Tem certeza?')) {
      this.http.post('/api/fontes/excluir', { id }).subscribe(() => {
        this.carregar();
      });
    }
  }
}
