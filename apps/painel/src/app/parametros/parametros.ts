import { Component, inject, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';

@Component({
  selector: 'app-parametros',
  imports: [CommonModule, FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule],
  templateUrl: './parametros.html',
  styleUrl: './parametros.scss',
})
export class Parametros implements OnInit {
  private http = inject(HttpClient);
  
  extrasTexto: string = '';

  ngOnInit() {
    this.http.get<{ extras: string[] }>('/api/parametros').subscribe(res => {
      this.extrasTexto = (res.extras || []).join('\n');
    });
  }

  salvar() {
    const extras = this.extrasTexto.split('\n').map(l => l.trim()).filter(l => l);
    this.http.post('/api/parametros', { extras }).subscribe(() => {
      alert('Salvo com sucesso!');
    });
  }
}
