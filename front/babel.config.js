module.exports = {
  presets: [
    //'babel-plugin-macros', // for stylesd components?
    '@babel/preset-env',
    ['@babel/preset-react', { runtime: 'automatic' }],
    '@babel/preset-typescript',
  ],
  plugins: ['babel-plugin-styled-components'],
};
