import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Coleta } from './coleta';

describe('Coleta', () => {
  let component: Coleta;
  let fixture: ComponentFixture<Coleta>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Coleta],
    }).compileComponents();

    fixture = TestBed.createComponent(Coleta);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
