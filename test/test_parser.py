#!/usr/bin/env python3
"""SemanticParser 单元测试"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evokb.parsing.parser import SemanticParser


def assert_kinds(units, expected):
    actual = [unit.kind for unit in units]
    assert actual == expected, f"期望 kinds={expected}，实际 {actual}"


def test_parse_c_semantic_units():
    parser = SemanticParser(min_lines=0)
    code = """#include <stdio.h>
/* node type */
struct Node {
    int value;
};

int counter = 1;

int foo(int a) {
    return a + counter;
}
"""

    units = parser.parse(code, "C")
    assert_kinds(units, ["type", "global", "function"])
    assert units[0].qualified_name == "Node"
    assert units[0].text.startswith("/* node type */\nstruct Node")
    assert units[0].start_line == 2 and units[0].end_line == 5
    assert units[1].qualified_name == "global::counter"
    assert units[2].qualified_name == "foo"
    assert not any(unit.kind == "signature" for unit in units)

    print("✓ test_parse_c_semantic_units passed")


def test_parsed_text_keeps_indentation_and_trims_only_boundaries():
    parser = SemanticParser(min_lines=0)
    code = """

   #include <stdio.h>

int foo() {
    return 0;
}   

"""

    units = parser.parse(code, "C")
    function_unit = next(unit for unit in units if unit.kind == "function")
    assert not any(unit.kind == "module" for unit in units)
    assert function_unit.text == "int foo() {\n    return 0;\n}"
    assert function_unit.start_line == 5 and function_unit.end_line == 7
    assert not any(unit.kind == "signature" for unit in units)

    print("✓ test_parsed_text_keeps_indentation_and_trims_only_boundaries passed")

def test_default_allows_single_line_units():
    parser = SemanticParser()
    code = """#include <stdio.h>
int counter = 1;

int foo() {
    return counter;
}
"""

    units = parser.parse(code, "C")
    kinds = [unit.kind for unit in units]
    assert "global" in kinds, f"expected global for single-line declaration, got {kinds}"
    assert "function" in kinds
    global_unit = next(u for u in units if u.kind == "global")
    assert global_unit.qualified_name == "global::counter"

    # min_lines=1 should still filter single-line units
    parser_strict = SemanticParser(min_lines=1)
    units_strict = parser_strict.parse(code, "C")
    assert [unit.kind for unit in units_strict] == ["function"]

    print("✓ test_default_allows_single_line_units passed")


def test_parse_cpp_nested_units():
    parser = SemanticParser(min_lines=0)
    code = """namespace N {
class A {
public:
    int f() { return 1; }
};
}
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "N::A" in qualified_names
    assert "N::A::f" in qualified_names
    assert not any(unit.kind == "module" for unit in units)
    assert not any(unit.kind == "signature" for unit in units)

    method_unit = next(unit for unit in units if unit.qualified_name == "N::A::f")
    assert method_unit.parent_qualified_name == "N::A"

    print("✓ test_parse_cpp_nested_units passed")


def test_parse_cpp17_nested_namespace():
    parser = SemanticParser(min_lines=0)
    code = """namespace A::B::C {
void f() { return; }
}
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "A::B::C::f" in qualified_names, f"期望 A::B::C::f，实际 {qualified_names}"

    f_unit = next(unit for unit in units if unit.qualified_name == "A::B::C::f")
    assert f_unit.parent_qualified_name == "A::B::C"

    print("✓ test_parse_cpp17_nested_namespace passed")


def test_parse_cpp_template_units():
    parser = SemanticParser(min_lines=0)
    code = """template <typename T>
class Box {
public:
    T value;
};

template <typename T>
inline T add(T a, T b) {
    return a + b;
}
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "Box" in qualified_names
    assert "add" in qualified_names

    box_unit = next(unit for unit in units if unit.qualified_name == "Box")
    add_unit = next(unit for unit in units if unit.qualified_name == "add")

    assert box_unit.text.startswith("template <typename T>\nclass Box"), "模板类前缀应并入 type 条目"
    assert add_unit.text.startswith(
        "template <typename T>\ninline T add"
    ), "模板函数前缀应并入 function 条目"
    assert not any(unit.kind == "signature" for unit in units)
    assert not any(unit.kind == "module" for unit in units), "module 条目不应入库"

    print("✓ test_parse_cpp_template_units passed")


def test_parse_cpp_recovered_macro_class_units():
    parser = SemanticParser(min_lines=0)
    code = """class BMD_PUBLIC IDeckLinkMemoryAllocator : public IUnknown
{
public:
    virtual HRESULT AllocateBuffer (uint32_t bufferSize, void** allocatedBuffer) = 0;
    virtual HRESULT ReleaseBuffer (void* buffer) = 0;
};
"""

    units = parser.parse(code, "C")
    type_unit = next(unit for unit in units if unit.kind == "type")

    assert type_unit.qualified_name == "IDeckLinkMemoryAllocator"
    assert type_unit.text.endswith("};"), "恢复出的类型条目应包含结尾分号"
    assert not any(unit.kind == "function" for unit in units), "宏修饰的 class 不应被识别为 function"

    print("✓ test_parse_cpp_recovered_macro_class_units passed")


def test_parse_cpp_recovered_midl_interface_units():
    parser = SemanticParser(min_lines=0)
    code = """MIDL_INTERFACE("BE2D9020-461E-442F-84B7-E949CB953B9D")
IDeckLinkOutput : public IUnknown
{
public:
    virtual HRESULT STDMETHODCALLTYPE DoesSupportVideoMode(
        BMDVideoConnection connection,
        BMDDisplayMode requestedMode) = 0;
};
"""

    units = parser.parse(code, "C")
    type_unit = next(unit for unit in units if unit.kind == "type")

    assert type_unit.qualified_name == "IDeckLinkOutput"
    assert type_unit.text.startswith("IDeckLinkOutput : public IUnknown")
    assert not any(
        unit.kind == "global" and unit.symbol_name == "IUnknown" for unit in units
    ), "MIDL 接口不应退化成 global::IUnknown"

    print("✓ test_parse_cpp_recovered_midl_interface_units passed")


def test_parse_cpp_exported_template_type_balances_to_full_class():
    parser = SemanticParser(min_lines=0)
    code = """template<>
class PCL_EXPORTS CropBox<pcl::PCLPointCloud2> : public FilterIndices<pcl::PCLPointCloud2>
{
public:
  CropBox (bool extract_removed_indices = false) :
    FilterIndices<pcl::PCLPointCloud2>::FilterIndices (extract_removed_indices)
  {
    filter_name_ = "CropBox";
  }
};
"""

    units = parser.parse(code, "C")
    type_unit = next(unit for unit in units if unit.kind == "type")

    assert type_unit.qualified_name == "CropBox"
    assert type_unit.text.endswith("};"), "恢复出的模板导出类应扩展到完整类结尾"
    assert not any(
        unit.kind == "function" and unit.qualified_name == "PCL_EXPORTS"
        for unit in units
    ), "导出宏不应被识别成 function 名称"

    print("✓ test_parse_cpp_exported_template_type_balances_to_full_class passed")


def test_filter_noise_only_tail_module():
    parser = SemanticParser(min_lines=0)
    code = """#endif

} // ipp

//! @endcond

//! @} core_utils

} // cv

#include "opencv2/core/neon_utils.hpp"
#include "opencv2/core/vsx_utils.hpp"
#include "opencv2/core/check.hpp"

#endif //OPENCV_CORE_BASE_HPP
"""

    units = parser.parse(code, "C")
    assert units == [], "不入库 module 后，纯尾巴文件不应生成条目"

    print("✓ test_filter_noise_only_tail_module passed")


def test_parse_c_macro_prototypes_balance_and_keep_names():
    parser = SemanticParser(min_lines=0)
    code = """/* Local functions for crc concatenation */
local unsigned int gf2_matrix_times OF((unsigned int *mat,
                                         unsigned int vec));
local void gf2_matrix_square OF((unsigned int *square, unsigned int *mat));
"""

    units = parser.parse(code, "C")
    assert len(units) >= 2, "宏原型声明应生成 global 条目"
    assert all(unit.kind == "global" for unit in units), "所有条目应为 global"
    assert "global::int" not in {unit.qualified_name for unit in units}

    square_unit = next(unit for unit in units if "gf2_matrix_square" in unit.text)
    assert square_unit.text.endswith("unsigned int *mat));")

    print("✓ test_parse_c_macro_prototypes_balance_and_keep_names passed")


def test_parse_error_for_loop_does_not_emit_global():
    parser = SemanticParser(min_lines=0)
    code = """return 0;
}
if(sorted[child_label].empty ()){
  noChildBlobVector(sorted, parent_label, child_number);
  return 0;
}
// go over all parents in this vector
for(std::size_t p = 0; p < sorted[parent_label].size(); p++){
  float best_value = std::numeric_limits<float>::max();
  int best_child_id = NO_CHILD;
}
"""

    units = parser.parse(code, "C")
    assert not any(unit.kind == "global" for unit in units), "for 头中的局部变量不应漂成 global"

    print("✓ test_parse_error_for_loop_does_not_emit_global passed")


def test_parse_java_nested_type_and_method():
    parser = SemanticParser(min_lines=0)
    code = """package sample;
class A {
    A() {}
    void f() {}
    static class B {}
}
"""

    units = parser.parse(code, "Java")
    qualified_names = {unit.qualified_name for unit in units}
    assert "A" in qualified_names
    assert "A::A" in qualified_names
    assert "A::f" in qualified_names
    assert "A::B" in qualified_names
    assert not any(unit.kind == "module" for unit in units)
    assert not any(unit.kind == "signature" for unit in units)

    print("✓ test_parse_java_nested_type_and_method passed")


def test_parse_c_declaration_block_units():
    parser = SemanticParser(min_lines=0)
    code = """int foo(int value) {
    int x = value;
    int y = x + 1;
    return y;
}
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "foo" in qualified_names
    assert "foo::declblock#1" in qualified_names

    declblock = next(unit for unit in units if unit.qualified_name == "foo::declblock#1")
    assert declblock.text == "    int x = value;\n    int y = x + 1;"
    assert declblock.start_line == 2 and declblock.end_line == 3

    print("✓ test_parse_c_declaration_block_units passed")


def test_parse_c_declaration_block_units_ignore_comments_between_locals():
    parser = SemanticParser(min_lines=0)
    code = """int foo(int value) {
    int x = value;
    // derived from x
    int y = x + 1;
    return y;
}
"""

    units = parser.parse(code, "C")
    declblock = next(unit for unit in units if unit.qualified_name == "foo::declblock#1")

    assert declblock.text == "    int x = value;\n    // derived from x\n    int y = x + 1;"
    assert declblock.start_line == 2 and declblock.end_line == 4

    print("✓ test_parse_c_declaration_block_units_ignore_comments_between_locals passed")


def test_parse_cpp_type_body_does_not_emit_declaration_block():
    parser = SemanticParser(min_lines=0)
    code = """class A {
public:
    int x;
    using Ptr = shared_ptr<A>;
    typedef int Index;
    int y;
    void f() override;
    bool operator==(const A& o) const;
    A();
    ~A();
};
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "A" in qualified_names
    assert not any(unit.kind == "declaration_block" for unit in units)

    print("✓ test_parse_cpp_type_body_does_not_emit_declaration_block passed")


def test_parse_cpp_macro_tail_does_not_emit_declaration_block():
    parser = SemanticParser(min_lines=0)
    code = """class OctreeLeafNode {
public:
  PCL_MAKE_ALIGNED_OPERATOR_NEW
};
"""

    units = parser.parse(code, "C")
    assert any(unit.kind == "type" for unit in units)
    assert not any(unit.kind == "declaration_block" for unit in units)

    print("✓ test_parse_cpp_macro_tail_does_not_emit_declaration_block passed")


def test_single_line_declaration_does_not_emit_declaration_block():
    parser = SemanticParser(min_lines=0)
    code = """int foo() {
    int value = 1;
    return value;
}
"""

    units = parser.parse(code, "C")
    assert not any(unit.kind == "declaration_block" for unit in units)

    print("✓ test_single_line_declaration_does_not_emit_declaration_block passed")


def test_error_recovery_type_like_symbol_name_is_reachable():
    parser = SemanticParser(min_lines=0)
    code = """EXPORT int;
"""

    units = parser.parse(code, "C")
    assert any(
        unit.kind == "global" and unit.symbol_name == "int" for unit in units
    ), "错误恢复时类型关键字可作为 symbol_name（TYPE_LIKE_SYMBOL_NAMES 检查非死代码）"

    print("✓ test_error_recovery_type_like_symbol_name_is_reachable passed")


def test_parse_cpp_class_with_multiple_methods():
    parser = SemanticParser(min_lines=0)
    code = """class Vector {
public:
    int x;
    int y;
    Vector(int x, int y) : x(x), y(y) {}
    int dot(const Vector& o) { return x*o.x + y*o.y; }
    int length() { return x*x + y*y; }
};
"""

    units = parser.parse(code, "C")
    qualified_names = {unit.qualified_name for unit in units}
    assert "Vector" in qualified_names, f"应包含 type Vector，实际 {qualified_names}"
    assert "Vector::Vector" in qualified_names, f"应包含构造函数，实际 {qualified_names}"
    assert "Vector::dot" in qualified_names, f"应包含 dot 方法，实际 {qualified_names}"
    assert "Vector::length" in qualified_names, f"应包含 length 方法，实际 {qualified_names}"

    for unit in units:
        if unit.qualified_name != "Vector":
            assert unit.parent_qualified_name == "Vector", (
                f"{unit.qualified_name} 的 parent 应为 Vector"
            )

    print("✓ test_parse_cpp_class_with_multiple_methods passed")


def test_parse_java_enum():
    parser = SemanticParser(min_lines=0)
    code = """enum Color {
    RED,
    GREEN,
    BLUE;

    public String display() {
        return name().toLowerCase();
    }
}
"""

    units = parser.parse(code, "Java")
    qualified_names = {unit.qualified_name for unit in units}
    assert "Color" in qualified_names, f"应包含 enum Color，实际 {qualified_names}"
    assert "Color::display" in qualified_names, f"应包含 display 方法，实际 {qualified_names}"

    print("✓ test_parse_java_enum passed")


def test_parse_java_interface():
    parser = SemanticParser(min_lines=0)
    code = """interface Comparable {
    int compareTo(Object o);
    default boolean isEqual(Object o) {
        return compareTo(o) == 0;
    }
}
"""

    units = parser.parse(code, "Java")
    qualified_names = {unit.qualified_name for unit in units}
    assert "Comparable" in qualified_names, f"应包含 interface Comparable，实际 {qualified_names}"

    print("✓ test_parse_java_interface passed")


def test_parse_empty_code():
    parser = SemanticParser()
    assert parser.parse("", "C") == []
    print("✓ test_parse_empty_code passed")


def main():
    print("Testing SemanticParser...")
    print("=" * 60)

    try:
        test_parse_c_semantic_units()
        test_parsed_text_keeps_indentation_and_trims_only_boundaries()
        test_default_allows_single_line_units()
        test_parse_cpp_nested_units()
        test_parse_cpp17_nested_namespace()
        test_parse_cpp_template_units()
        test_parse_cpp_recovered_macro_class_units()
        test_parse_cpp_recovered_midl_interface_units()
        test_parse_cpp_exported_template_type_balances_to_full_class()
        test_filter_noise_only_tail_module()
        test_parse_c_macro_prototypes_balance_and_keep_names()
        test_parse_error_for_loop_does_not_emit_global()
        test_parse_java_nested_type_and_method()
        test_parse_c_declaration_block_units()
        test_parse_c_declaration_block_units_ignore_comments_between_locals()
        test_parse_cpp_type_body_does_not_emit_declaration_block()
        test_parse_cpp_macro_tail_does_not_emit_declaration_block()
        test_single_line_declaration_does_not_emit_declaration_block()
        test_error_recovery_type_like_symbol_name_is_reachable()
        test_parse_cpp_class_with_multiple_methods()
        test_parse_java_enum()
        test_parse_java_interface()
        test_parse_empty_code()

        print("=" * 60)
        print("✓ All SemanticParser tests passed!")
        return 0
    except AssertionError as exc:
        print("=" * 60)
        print(f"✗ Test failed: {exc}")
        return 1
    except Exception as exc:
        print("=" * 60)
        print(f"✗ Unexpected error: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
