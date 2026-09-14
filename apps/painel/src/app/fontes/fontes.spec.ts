import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Fontes } from './fontes';

describe('Fontes', () => {
  let component: Fontes;
  let fixture: ComponentFixture<Fontes>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Fontes],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(Fontes);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
