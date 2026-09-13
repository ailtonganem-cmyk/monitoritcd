import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Parametros } from './parametros';

describe('Parametros', () => {
  let component: Parametros;
  let fixture: ComponentFixture<Parametros>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Parametros],
    }).compileComponents();

    fixture = TestBed.createComponent(Parametros);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
