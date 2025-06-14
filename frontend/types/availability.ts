export type SlotAction = 'add' | 'remove' | 'update';

export interface SlotOperation {
  action: SlotAction;
  // For add/update:
  date?: string;
  start_time?: string;
  end_time?: string;
  // For remove/update:
  slot_id?: number;
}

export interface BulkUpdateRequest {
  operations: SlotOperation[];
  validate_only?: boolean;
}

export interface OperationResult {
  operation_index: number;
  action: string;
  status: 'success' | 'failed' | 'skipped';
  reason?: string;
  slot_id?: number;
}

export interface BulkUpdateResponse {
  successful: number;
  failed: number;
  skipped: number;
  results: OperationResult[];
}

// For tracking existing slots
export interface ExistingSlot {
  id: number;
  date: string;
  start_time: string;
  end_time: string;
}

// Validation types
export interface ValidationSlotDetail {
    operation_index: number;
    action: string;
    date?: string;
    start_time?: string;
    end_time?: string;
    slot_id?: number;
    reason?: string;
    conflicts_with?: Array<{
      booking_id: number;
      start_time: string;
      end_time: string;
    }>;
  }
  
  export interface ValidationSummary {
    total_operations: number;
    valid_operations: number;
    invalid_operations: number;
    operations_by_type: Record<string, number>;
    has_conflicts: boolean;
    estimated_changes: {
      slots_added: number;
      slots_removed: number;
      conflicts: number;
    };
  }
  
  export interface WeekValidationResponse {
    valid: boolean;
    summary: ValidationSummary;
    details: ValidationSlotDetail[];
    warnings: string[];
  }

  export interface TimeSlot {
    start_time: string;
    end_time: string;
    is_available: boolean;
  }

  export interface WeekSchedule {
    [date: string]: TimeSlot[];
  }
  
  export interface ValidateWeekRequest {
    current_week: WeekSchedule;
    saved_week: WeekSchedule;
    week_start: string; // ISO date string
  }