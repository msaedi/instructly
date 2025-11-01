import { render } from '@testing-library/react';
import React from 'react';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '@/components/ui/select';

describe('Select component', () => {
  it('does not emit modal attribute warnings when open', () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <Select defaultOpen value="one">
        <SelectTrigger>
          <SelectValue placeholder="Pick one" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="one">One</SelectItem>
          <SelectItem value="two">Two</SelectItem>
        </SelectContent>
      </Select>
    );

    const errorCalls = errorSpy.mock.calls
      .flat()
      .filter((message) => typeof message === 'string' && message.includes('non-boolean attribute `modal`'));
    expect(errorCalls).toHaveLength(0);

    errorSpy.mockRestore();
  });
});
