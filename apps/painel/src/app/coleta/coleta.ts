import { Component, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';

@Component({
  selector: 'app-coleta',
  imports: [CommonModule, FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatCheckboxModule],
  templateUrl: './coleta.html',
  styleUrl: './coleta.scss',
})
export class Coleta {
  private http = inject(HttpClient);

  sourceId: string = '';
  dryRun: boolean = true;
  comando: string = '';

  coletar() {
    this.http.post<{ comando: string }>('/api/coleta', { source_id: this.sourceId, dry_run: this.dryRun }).subscribe(res => {
      this.comando = res.comando;
    });
  }
}
