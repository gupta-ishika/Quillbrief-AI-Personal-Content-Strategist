import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import App from './App';

describe('App', () => {
  it('renders the application title', () => {
    render(<App />);
    expect(screen.getByText('AI Personal Content Strategist')).toBeInTheDocument();
  });

  it('renders the setup confirmation banner', () => {
    render(<App />);
    expect(
      screen.getByText(/Frontend setup complete/i)
    ).toBeInTheDocument();
  });
});
