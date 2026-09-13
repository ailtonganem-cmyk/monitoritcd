import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';

interface IaItem {
  id?: string;
  nome?: string;
  habilitado: boolean;
  modelo: string;
  esforco: string;
}

@Component({
  selector: 'app-ia',
  imports: [CommonModule, FormsModule, MatCardModule, MatCheckboxModule, MatFormFieldModule, MatSelectModule, MatInputModule, MatButtonModule],
  templateUrl: './ia.html',
  styleUrl: './ia.scss',
})
export class Ia implements OnInit {
  private http = inject(HttpClient);
  
  itens: IaItem[] = [];
  catalogo: any = {};

  ngOnInit() {
    this.http.get<{ itens: IaItem[], catalogo: any }>('/api/ia').subscribe(res => {
      this.itens = res.itens || [];
      this.catalogo = res.catalogo || {};
    });
  }

  salvar() {
    this.http.post('/api/ia', { itens: this.itens }).subscribe(() => {
      alert('Salvo com sucesso!');
    });
  }
}
