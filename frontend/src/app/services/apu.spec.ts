import { TestBed } from '@angular/core/testing';

import { ApuService } from './apu';

describe('ApuService', () => {
  let service: ApuService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(ApuService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});