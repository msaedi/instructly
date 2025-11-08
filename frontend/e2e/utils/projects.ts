type ProjectCarrier = { project: { name: string } };

export const isInstructor = (info: ProjectCarrier): boolean => info.project.name === 'instructor';
export const isAdmin = (info: ProjectCarrier): boolean => info.project.name === 'admin';
export const isAnon = (info: ProjectCarrier): boolean => info.project.name === 'anon';
