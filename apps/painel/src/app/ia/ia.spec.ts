import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Ia } from './ia';

describe('Ia', () => {
  let component: Ia;
  let fixture: ComponentFixture<Ia>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Ia],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();

    fixture = TestBed.createComponent(Ia);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
