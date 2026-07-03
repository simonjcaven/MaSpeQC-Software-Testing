from lxml import etree

def deep_hierarchy_roundtrip(input_path: str, output_path: str):
    """
    reads an xml with a deep hierarchy
    allows modification on every level before writing the xml elements to a file
    memory consumption is independend of the file size
    """
    
    # listen for the 'start' and 'end' tag of every element
    context = etree.iterparse(input_path, events=('start', 'end'))
    
    with etree.xmlfile(output_path, encoding='utf-8') as xf:
        
        for event, elem in context:
            if event == 'start':
                # opening tag
                
                # ---------------------------------------------------
                # modify attributes when element starts
                # 
                # if elem.tag == "...":
                #     elem.set("status", "updated")
                # ---------------------------------------------------
                
                # write tag to file
                xf.start_element(elem.tag, attrib=dict(elem.attrib))
                
            elif event == 'end':
                # closing tag
                # text content end child elements are available
                
                # write text content if available
                if elem.text:
                    xf.write_text(elem.text)
                
                # ---------------------------------------------------
                # modify text content
                # if elem.tag == "..." and elem.text:
                #     elem.text = "new content"
                #     xf.write_text(elem.text)
                # ---------------------------------------------------
                
                # write tag to file
                xf.end_element(elem.tag)
                
                # write tail text if available
                if elem.tail:
                    xf.write_text(elem.tail)
                
                # clear memory for this element
                elem.clear()
                
                # by default the parser stores parent child relations
                # delete processed siblings
                while elem.getprevious() is not None:
                    del elem.getparent()[0]
