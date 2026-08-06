/**
 * Theme Mantine — SDD 08 §8.
 *
 * Không tự viết design system: Mantine đã đủ. File này chỉ khai những thứ
 * Mantine không biết — và tất cả đều là quyết định về *ý nghĩa*, không phải
 * về thẩm mỹ.
 */

import { createTheme, type MantineColorsTuple } from '@mantine/core';

/**
 * `certus` — màu chủ đạo. Xanh mực, đủ trung tính để KHÔNG bị nhầm với xanh
 * lá của band `high` hay đỏ của cảnh báo. Màu thương hiệu không được mượn
 * ngữ nghĩa của màu trạng thái.
 */
const certus: MantineColorsTuple = [
  '#eef3ff',
  '#dce4f5',
  '#b9c7e2',
  '#94a8d0',
  '#748dc0',
  '#5f7cb7',
  '#5474b4',
  '#44639f',
  '#3a578f',
  '#2c4b80',
];

export const theme = createTheme({
  primaryColor: 'certus',
  colors: { certus },
  fontFamily:
    'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif',
  fontFamilyMonospace:
    'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace',
  headings: { fontWeight: '650' },
  defaultRadius: 'md',
});

/** Khẩu hiệu sản phẩm tự in ra màn hình — system-design §0. */
export const TAGLINE = 'Certus — chúng tôi không đoán.';

/**
 * Câu phải in dưới ba khối mẫu số. Đặt ở đây vì nó là một hằng số của SẢN
 * PHẨM, không phải một chuỗi trang trí của component.
 */
export const THREE_LAYER_LESSON =
  'Ba con số này đo ba thứ khác nhau. Chúng không thay thế nhau.';
